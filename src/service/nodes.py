import os
import httpx
import asyncio
from typing import Dict, Any, List, Optional

PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 'http://localhost:9090')

WORKER_NODES = {"192.168.10.11", "192.168.10.12", "192.168.10.3", "192.168.10.4"}

def format_uptime(seconds: float) -> str:
    if seconds <= 0: return "0d 0h 0m"
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(days)}d {int(hours)}h {int(minutes)}m"

def strip_port(instance: str) -> str:
    return instance.split(':')[0] if instance else "unknown"

async def query_prometheus(client: httpx.AsyncClient, query: str) -> List[Dict]:
    try:
        response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            return data["data"]["result"]
    except Exception as e:
        print(f"Prometheus query failed for {query}: {e}")
    return []

# -------------------------------------------------------------
# ENDPOINT 1: LIGHTWEIGHT SUMMARY LIST
# -------------------------------------------------------------
async def get_nodes_summary() -> List[Dict[str, Any]]:
    """Fetches high-level metrics for all worker cards."""
    queries = {
        "up": 'up{job="node_exporter"}',
        "uptime": 'time() - node_boot_time_seconds',
        "cpu_usage": '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "mem_total": 'node_memory_MemTotal_bytes',
        "mem_avail": 'node_memory_MemAvailable_bytes',
        "gpu_avg_util": 'avg by (instance) (nvidia_gpu_duty_cycle)'
    }

    async with httpx.AsyncClient() as client:
        tasks = [query_prometheus(client, q) for q in queries.values()]
        results = await asyncio.gather(*tasks)
        up_data, uptime_data, cpu_data, mem_total, mem_avail, gpu_avg = results

    nodes_map: Dict[str, Dict] = {}

    for item in up_data:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip not in WORKER_NODES: continue
        
        nodes_map[ip] = {
            "id": ip,
            "name": f"worker-{ip.split('.')[-1]}",
            "status": "Online" if int(item["value"][1]) == 1 else "Offline",
            "uptime": "0d 0h 0m",
            "cpuUsage": 0,
            "memoryUsed": 0,
            "memoryTotal": 0,
            "avgGpuUsage": 0
        }

    # Map remaining high-level attributes
    for item in uptime_data:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map: nodes_map[ip]["uptime"] = format_uptime(float(item["value"][1]))

    for item in cpu_data:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map: nodes_map[ip]["cpuUsage"] = round(float(item["value"][1]), 1)

    for item in gpu_avg:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map: nodes_map[ip]["avgGpuUsage"] = round(float(item["value"][1]))

    # Compute quick RAM stats
    for item in mem_total:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map: nodes_map[ip]["memoryTotal"] = round(float(item["value"][1]) / (1024**3))
            
    for item in mem_avail:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map:
            total = nodes_map[ip]["memoryTotal"]
            used = total - (float(item["value"][1]) / (1024**3))
            nodes_map[ip]["memoryUsed"] = round(used)

    return list(nodes_map.values())

# -------------------------------------------------------------
# ENDPOINT 2: DEEP-DIVE FOR A SINGLE NODE
# -------------------------------------------------------------
async def get_node_details(node_id: str) -> Optional[Dict[str, Any]]:
    """Fetches comprehensive, granular metrics for one specific node."""
    if node_id not in WORKER_NODES:
        return None

    # Notice how we append filter strings like {instance=~"{node_id}.*"} 
    # to pull metrics ONLY related to this individual machine.
    queries = {
        "up": f'up{{instance=~"{node_id}.*"}}',
        "uptime": f'time() - node_boot_time_seconds{{instance=~"{node_id}.*"}}',
        "cpu_usage": f'100 - (avg(rate(node_cpu_seconds_total{{instance=~"{node_id}.*", mode="idle"}}[5m])) * 100)',
        "cpu_cores": f'count(count by (core) (node_cpu_seconds_total{{instance=~"{node_id}.*"}}))',
        "mem_total": f'node_memory_MemTotal_bytes{{instance=~"{node_id}.*"}}',
        "mem_avail": f'node_memory_MemAvailable_bytes{{instance=~"{node_id}.*"}}',
        
        # Scoped GPU Details
        "gpu_util": f'nvidia_gpu_duty_cycle{{instance=~"{node_id}.*"}}',
        "gpu_mem_used": f'nvidia_gpu_memory_used_bytes{{instance=~"{node_id}.*"}}',
        "gpu_mem_total": f'nvidia_gpu_memory_total_bytes{{instance=~"{node_id}.*"}}',
        "gpu_temp": f'nvidia_gpu_temperature_celsius{{instance=~"{node_id}.*"}}',
        "gpu_power": f'nvidia_gpu_power_draw_watts{{instance=~"{node_id}.*"}}',
        "gpu_info": f'nvidia_gpu_name{{instance=~"{node_id}.*"}}'
    }

    async with httpx.AsyncClient() as client:
        tasks = [query_prometheus(client, q) for q in queries.values()]
        results = await asyncio.gather(*tasks)
        
        (up_data, uptime_data, cpu_data, cpu_cores, mem_total, mem_avail,
         gpu_util, gpu_mem_used, gpu_mem_total, gpu_temp, gpu_power, gpu_info) = results

    # If even basic status isn't reporting, the node might be entirely down
    is_up = any(int(item["value"][1]) == 1 for item in up_data if "node_exporter" in item["metric"].get("job", ""))

    node_details = {
        "id": node_id,
        "name": f"worker-{node_id.split('.')[-1]}",
        "status": "Online" if is_up else "Offline",
        "uptime": format_uptime(float(uptime_data[0]["value"][1])) if uptime_data else "0d 0h 0m",
        "cpuModel": "AMD EPYC or Intel Xeon", # Static or configured depending on hardware inventory
        "cpuCores": int(cpu_cores[0]["value"][1]) if cpu_cores else 0,
        "cpuUsage": round(float(cpu_data[0]["value"][1]), 1) if cpu_data else 0,
        "memoryTotal": round(float(mem_total[0]["value"][1]) / (1024**3)) if mem_total else 0,
        "memoryUsed": 0,
        "gpus": []
    }

    if mem_total and mem_avail:
        total_gb = float(mem_total[0]["value"][1]) / (1024**3)
        avail_gb = float(mem_avail[0]["value"][1]) / (1024**3)
        node_details["memoryUsed"] = round(total_gb - avail_gb)

    # Compile GPU Sub-objects
    gpus_map = {}
    for item in gpu_info:
        uuid = item["metric"].get("uuid", "")
        gpus_map[uuid] = {
            "id": uuid[-8:],
            "model": item["metric"].get("name", "NVIDIA GPU"),
            "utilization": 0, "memoryUsed": 0, "memoryTotal": 0, "temperature": 0, "powerDraw": 0
        }

    def fill_gpu(dataset, target_key, divisor=1):
        for item in dataset:
            uuid = item["metric"].get("uuid", "")
            if uuid in gpus_map:
                gpus_map[uuid][target_key] = round(float(item["value"][1]) / divisor)

    fill_gpu(gpu_util, "utilization")
    fill_gpu(gpu_mem_used, "memoryUsed", 1024**3)
    fill_gpu(gpu_mem_total, "memoryTotal", 1024**3)
    fill_gpu(gpu_temp, "temperature")
    fill_gpu(gpu_power, "powerDraw")

    gpu_list = list(gpus_map.values())
    gpu_list.sort(key=lambda x: x["id"])
    node_details["gpus"] = gpu_list

    return node_details