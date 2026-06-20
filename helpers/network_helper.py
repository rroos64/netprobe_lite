# Network tests
import subprocess
import json
import os
import time
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import dns.resolver
import requests


class NetworkCollector(object): # Main network collection class

    def __init__(self,sites,count,dns_test_site,nameservers_external):
        self.sites = sites # List of sites to ping
        self.count = str(count) # Number of pings
        self.stats = [] # List of stat dicts
        self.dnsstats = [] # List of stat dicts
        self.dns_test_site = dns_test_site # Site used to test DNS response times
        self.nameservers = []
        self.nameservers = nameservers_external


    def pingtest(self,count,site):

        ping = subprocess.getoutput(f"ping -n -i 0.1 -c {count} {site} | grep 'rtt\|loss'")

        try:
            loss = ping.split(' ')[5].strip('%')
            latency=ping.split('/')[4]
            jitter=ping.split('/')[6].split(' ')[0]

            netdata = {
                "site":site,
                "latency":latency,
                "loss":loss,
                "jitter":jitter
            }

            self.stats.append(netdata)

        except:
            print(f"Error pinging {site}")
            return False

        return True

    def dnstest(self,site,nameserver):
        
        my_resolver = dns.resolver.Resolver()

        server = [] # Resolver needs a list
        server.append(nameserver[1])


        try:

            my_resolver.nameservers = server
            my_resolver.timeout = 10

            answers = my_resolver.query(site,'A')

            dns_latency = round(answers.response.time * 1000,2)

            dnsdata = {
                "nameserver":nameserver[0],
                "nameserver_ip":nameserver[1],
                "latency":dns_latency
            }

            self.dnsstats.append(dnsdata)

        except Exception as e:
            print(f"Error performing DNS resolution on {nameserver}")
            print(e)

            dnsdata = {
                "nameserver":nameserver[0],
                "nameserver_ip":nameserver[1],
                "latency":5000
            }
            
            self.dnsstats.append(dnsdata)

        return True

    def collect(self):

        # Empty preveious results
        self.stats = []
        self.dnsstats = []

        # Create threads, start them
        threads = []

        for item in self.sites:
            t = Thread(target=self.pingtest, args=(self.count,item,))
            threads.append(t)
            t.start()

        # Wait for threads to complete
        for t in threads:
            t.join()

        # Create threads, start them
        threads = []            

        for item in self.nameservers:
            s = Thread(target=self.dnstest, args=(self.dns_test_site,item,))
            threads.append(s)
            s.start()            

        # Wait for threads to complete
        for s in threads:
            s.join()

        results = json.dumps({
            "stats":self.stats,
            "dns_stats":self.dnsstats
        })

        return results


class Netprobe_Speedtest(object): # Speed test class

    def __init__(self,provider="cloudflare"):
        self.speedtest_stats = {"download": None, "upload": None}
        self.provider = provider

    def get_closest_servers(self):

        completed = subprocess.run(
            [
                "speedtest",
                "--servers",
                "--format=json",
                "--accept-license",
                "--accept-gdpr"
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )

        server_list = json.loads(completed.stdout)

        return [server["id"] for server in server_list["servers"]]

    def ookla_speedtest(self):

        last_error = None

        # The nearest Ookla server is often a small regional ISP node that
        # intermittently fails the multi-connection throughput stage. Retry
        # immediately against the next-closest server instead of waiting
        # for the next probe interval.
        for server_id in self.get_closest_servers():

            try:
                completed = subprocess.run(
                    [
                        "speedtest",
                        "--format=json",
                        "--accept-license",
                        "--accept-gdpr",
                        f"--server-id={server_id}"
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=60
                )

                speedtest_result = json.loads(completed.stdout)

                # Ookla's official CLI returns bandwidth in bytes/second.
                # Prometheus/Grafana expects this metric in bits/second.
                download = speedtest_result["download"]["bandwidth"] * 8
                upload = speedtest_result["upload"]["bandwidth"] * 8

                self.speedtest_stats = {
                    "download": download,
                    "upload": upload
                }

                return

            except Exception as e:
                last_error = e
                continue

        raise last_error

    def cloudflare_download(self,size):

        response = requests.get(
            f"https://speed.cloudflare.com/__down?bytes={size}",
            timeout=30
        )
        response.raise_for_status()

        return len(response.content)

    def cloudflare_upload(self,size):

        response = requests.post(
            "https://speed.cloudflare.com/__up",
            data=os.urandom(size),
            timeout=30
        )
        response.raise_for_status()

        return size

    def cloudflare_speedtest(self):

        # Cloudflare's speed test runs entirely over HTTPS (no raw-socket
        # multi-connection protocol like Ookla's), avoiding the port 8080
        # multi-connection failures seen against regional Ookla servers.
        #
        # A single cold connection measures far below real line speed,
        # since TLS handshake and TCP slow-start eat into the timed
        # window. Run an untimed warm-up round first, then measure
        # several parallel streams (matching how speedtest websites
        # saturate high-bandwidth links) and sum their throughput.
        streams = 4
        warmup_bytes = 1_000_000
        download_bytes = 25_000_000
        upload_bytes = 10_000_000

        with ThreadPoolExecutor(max_workers=streams) as executor:
            list(executor.map(self.cloudflare_download,[warmup_bytes]*streams))

        start = time.time()
        with ThreadPoolExecutor(max_workers=streams) as executor:
            sizes = list(executor.map(self.cloudflare_download,[download_bytes]*streams))
        elapsed = time.time() - start
        download_bandwidth = sum(sizes) / elapsed # bytes/sec

        with ThreadPoolExecutor(max_workers=streams) as executor:
            list(executor.map(self.cloudflare_upload,[warmup_bytes]*streams))

        start = time.time()
        with ThreadPoolExecutor(max_workers=streams) as executor:
            sizes = list(executor.map(self.cloudflare_upload,[upload_bytes]*streams))
        elapsed = time.time() - start
        upload_bandwidth = sum(sizes) / elapsed # bytes/sec

        self.speedtest_stats = {
            "download": download_bandwidth * 8,
            "upload": upload_bandwidth * 8
        }

    def collect(self):

        self.speedtest_stats = {"download": None, "upload": None}

        if self.provider == "cloudflare":
            self.cloudflare_speedtest()
        else:
            self.ookla_speedtest()

        results = json.dumps({
            "speed_stats":self.speedtest_stats
        })

        return results







