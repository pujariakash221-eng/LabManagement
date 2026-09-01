"""Safe, manual local-network discovery for the operator dashboard."""

import ipaddress
import logging
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DiscoveredDevice(BaseModel):
    """A host found during the latest manual discovery scan."""

    ip_address: str
    hostname: str | None = None
    reachable: bool


@dataclass(frozen=True)
class NetworkInfo:
    """The local address and subnet selected for discovery."""

    local_ip: str
    subnet: ipaddress.IPv4Network


def get_local_ip() -> str:
    """Determine the preferred local address without sending application data."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def get_interface_netmask(interface: str) -> str | None:
    """Read a Linux interface netmask when available."""
    if platform.system() != "Linux":
        return None
    try:
        with open(f"/sys/class/net/{interface}/netmask", encoding="utf-8") as netmask_file:
            return netmask_file.read().strip()
    except (FileNotFoundError, OSError):
        return None


def get_default_interface() -> str | None:
    """Find the interface used by the default route on Linux."""
    try:
        with open("/proc/net/route", encoding="utf-8") as route_file:
            for line in route_file.readlines()[1:]:
                fields = line.split()
                if len(fields) > 1 and fields[1] == "00000000":
                    return fields[0]
    except (FileNotFoundError, OSError):
        return None
    return None


def determine_network() -> NetworkInfo:
    """Select the local subnet, falling back to a conventional /24 mask."""
    local_ip = get_local_ip()
    netmask = get_interface_netmask(get_default_interface() or "")
    try:
        subnet = ipaddress.ip_network(f"{local_ip}/{netmask or '24'}", strict=False)
    except ValueError:
        subnet = ipaddress.ip_network("127.0.0.0/8")
    return NetworkInfo(local_ip=local_ip, subnet=subnet)


def resolve_hostname(ip_address: str) -> str | None:
    """Resolve a hostname without failing the discovery scan."""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip_address)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return None


def ping_host(ip_address: str, timeout_seconds: float = 0.4) -> bool:
    """Send one ICMP echo request using the platform ping utility."""
    if ip_address == "127.0.0.1":
        return True
    if platform.system() == "Windows":
        command = ["ping", "-n", "1", "-w", str(int(timeout_seconds * 1000)), ip_address]
    else:
        command = ["ping", "-c", "1", "-W", str(max(1, int(timeout_seconds))), ip_address]
    try:
        return subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout_seconds + 0.5,
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def discover_devices() -> list[DiscoveredDevice]:
    """Perform one bounded manual ICMP sweep of the selected local subnet."""
    network = determine_network()
    addresses = [str(address) for address in network.subnet.hosts()]
    if network.local_ip not in addresses:
        addresses.append(network.local_ip)

    devices: list[DiscoveredDevice] = []
    with ThreadPoolExecutor(max_workers=min(32, max(1, len(addresses)))) as executor:
        checks = {executor.submit(ping_host, address): address for address in addresses}
        for check in as_completed(checks):
            address = checks[check]
            try:
                reachable = check.result()
            except OSError:
                reachable = False
            if reachable:
                devices.append(
                    DiscoveredDevice(
                        ip_address=address,
                        hostname=resolve_hostname(address),
                        reachable=True,
                    )
                )

    devices.sort(key=lambda device: ipaddress.ip_address(device.ip_address))
    logger.info("Discovery scan completed for %s: %d reachable host(s)", network.subnet, len(devices))
    return devices
