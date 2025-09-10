import socket, time
from fastapi import APIRouter
import os

router = APIRouter()

# Fetch variables
USER = os.getenv("user", "postgres")
PASSWORD = os.getenv("password", "DivineRayys@2025")
HOST = os.getenv("host", "db.zjgzqudobxmqgulyhgft.supabase.co")
PORT = os.getenv("port", "5432")
DBNAME = os.getenv("dbname", "postgres")

@router.get("/_db_debug_info")
def _db_debug_info():
    host = HOST
    port = int(PORT or 5432)
    result = {"host": host, "port": port, "resolved": [], "connect_attempts": []}

    # Resolve both families
    try:
        addrs = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        # Deduplicate sockaddr
        seen = set()
        for ai in addrs:
            fam = ai[0]
            sockaddr = ai[4]
            ip = sockaddr[0]
            if ip in seen:
                continue
            seen.add(ip)
            result["resolved"].append({"family": "AF_INET" if fam==socket.AF_INET else "AF_INET6", "ip": ip})
    except Exception as e:
        result["resolve_error"] = str(e)
        return result

    # Attempt short TCP connect to each resolved IP (no TLS/DB handshake)
    for entry in result["resolved"]:
        ip = entry["ip"]
        fam = socket.AF_INET if ":" not in ip else socket.AF_INET6
        info = {"ip": ip}
        start = time.time()
        s = None
        try:
            s = socket.socket(fam, socket.SOCK_STREAM)
            s.settimeout(5.0)  # 5s timeout
            s.connect((ip, port))
            elapsed = time.time() - start
            info["ok"] = True
            info["elapsed"] = round(elapsed, 3)
        except Exception as e:
            elapsed = time.time() - start
            info["ok"] = False
            info["error"] = str(e)
            info["elapsed"] = round(elapsed, 3)
        finally:
            try:
                if s:
                    s.close()
            except:
                pass
        result["connect_attempts"].append(info)

    return result


