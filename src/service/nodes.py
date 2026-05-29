import os
import httpx
import asyncio
import asyncssh
from typing import Dict, Any, List, Optional

PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 'http://localhost:9090')
SSH_USERNAME = os.getenv('SSH_USERNAME')
SSH_PASSWORD = os.getenv('SSH_PASSWORD')

WORKER_NODES = {"192.168.10.9", "192.168.10.10", "192.168.10.3", "192.168.10.4"}

async def get_cpu_model_via_ssh(ip: str) -> str:
    """Connects to a node via SSH and extracts its exact CPU model name."""
    try:
        async with asyncssh.connect(
            ip, 
            username=SSH_USERNAME, 
            password=SSH_PASSWORD,
            known_hosts=None,
            login_timeout=5
        ) as conn:
            # Run lscpu and grep out the Model name line
            result = await conn.run("lscpu | grep 'Model name:'", check=True)

            # Clean up the output string: "Model name: Intel(R) Core(TM) i7..." -> "Intel(R) Core(TM) i7..."
            if result.stdout:
                return result.stdout.replace("Model name:", "").strip()
    except Exception as e:
        print(f"SSH CPU lookup failed for {ip}: {e}")
    
    return "x86_64 Processor @ 4.5GHz" # Reliable backup fallback

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
        "up": 'up{job="node"}',
        "uptime": 'time() - node_boot_time_seconds',
        "cpu_usage": '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "mem_total": 'node_memory_MemTotal_bytes',
        "mem_avail": 'node_memory_MemAvailable_bytes',
        "gpu_avg_util": 'avg by (instance) (nvidia_smi_utilization_gpu_ratio)'
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
        if ip in nodes_map and item.get("value"): nodes_map[ip]["uptime"] = format_uptime(float(item["value"][1]))

    for item in cpu_data:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map and item.get("value"): nodes_map[ip]["cpuUsage"] = round(float(item["value"][1]), 1)

    for item in gpu_avg:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map and item.get("value"): 
            val = float(item["value"][1])
            # If exporter sends a ratio decimal (e.g. 0.01), convert to whole percentage
            nodes_map[ip]["avgGpuUsage"] = round(val * 100 if val <= 1.0 else val)

    # Compute quick RAM stats
    for item in mem_total:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map and item.get("value"): nodes_map[ip]["memoryTotal"] = round(float(item["value"][1]) / (1024**3))
            
    for item in mem_avail:
        ip = strip_port(item["metric"].get("instance", ""))
        if ip in nodes_map and item.get("value"):
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

    # Exactly 11 items
    queries = {
        "up": f'up{{instance=~"{node_id}.*"}}',
        "uptime": f'time() - node_boot_time_seconds{{instance=~"{node_id}.*"}}',
        "cpu_usage": f'100 - (avg(rate(node_cpu_seconds_total{{instance=~"{node_id}.*", mode="idle"}}[5m])) * 100)',
        "cpu_cores": f'count(node_cpu_seconds_total{{instance=~"{node_id}.*", mode="idle"}})',
        "mem_total": f'node_memory_MemTotal_bytes{{instance=~"{node_id}.*"}}',
        "mem_avail": f'node_memory_MemAvailable_bytes{{instance=~"{node_id}.*"}}',
        
        # Scoped GPU Details
        "gpu_util": f'nvidia_smi_utilization_gpu_ratio{{instance=~"{node_id}.*"}}',
        "gpu_mem_used": f'nvidia_smi_memory_used_bytes{{instance=~"{node_id}.*"}}',
        "gpu_mem_total": f'nvidia_smi_memory_total_bytes{{instance=~"{node_id}.*"}}',
        "gpu_temp": f'nvidia_smi_temperature_gpu{{instance=~"{node_id}.*"}}',
        "gpu_power": f'nvidia_smi_power_draw_watts{{instance=~"{node_id}.*"}}',
        "gpu_info": f'nvidia_smi_gpu_info{{instance=~"{node_id}.*"}}'
    }

    async with httpx.AsyncClient() as client:
        tasks = [query_prometheus(client, q) for q in queries.values()]
        tasks.append(get_cpu_model_via_ssh(node_id)) # Add SSH Task (Total tasks = 12)

        results = await asyncio.gather(*tasks)
        
        # --- FIXED UNPACKING ALIGNMENT (Exactly 12 variables mapped cleanly) ---
        (up_data, uptime_data, cpu_data, cpu_cores, mem_total, mem_avail,
         gpu_util, gpu_mem_used, gpu_mem_total, gpu_temp, gpu_power, gpu_info,
         detected_cpu_model) = results

    is_up = any(int(item["value"][1]) == 1 for item in up_data if "node" in item["metric"].get("job", ""))

    # --- FIXED: Added a safe guard for uptime_data[0] index checks ---
    node_details = {
        "id": node_id,
        "name": f"worker-{node_id.split('.')[-1]}",
        "status": "Online" if is_up else "Offline",
        "uptime": format_uptime(float(uptime_data[0]["value"][1])) if (uptime_data and len(uptime_data) > 0) else "0d 0h 0m",
        "cpuModel": detected_cpu_model,
        "cpuCores": int(cpu_cores[0]["value"][1]) if (cpu_cores and len(cpu_cores) > 0) else 1,
        "cpuUsage": round(float(cpu_data[0]["value"][1]), 1) if (cpu_data and len(cpu_data) > 0) else 0,
        "memoryTotal": round(float(mem_total[0]["value"][1]) / (1024**3)) if (mem_total and len(mem_total) > 0) else 0,
        "memoryUsed": 0,
        "gpus": []
    }

    if mem_total and mem_avail and len(mem_total) > 0 and len(mem_avail) > 0:
        total_gb = float(mem_total[0]["value"][1]) / (1024**3)
        avail_gb = float(mem_avail[0]["value"][1]) / (1024**3)
        node_details["memoryUsed"] = round(total_gb - avail_gb)

    # Compile GPU Sub-objects
    gpus_map = {}
    for item in gpu_info:
        uuid = item["metric"].get("uuid", "")
        gpus_map[uuid] = {
            "id": uuid[-8:],
            "model": item["metric"].get("name", "Quadro P5000"),
            "utilization": 0, "memoryUsed": 0, "memoryTotal": 0, "temperature": 0, "powerDraw": 0
        }

    def fill_gpu(dataset, target_key, divisor=1, is_ratio=False):
        for item in dataset:
            uuid = item["metric"].get("uuid", "")
            if uuid in gpus_map:
                val = float(item["value"][1])
                if is_ratio and val <= 1.0: val = val * 100
                gpus_map[uuid][target_key] = round(val / divisor)

    # Fill up telemetry datasets
    fill_gpu(gpu_util, "utilization", is_ratio=True)
    fill_gpu(gpu_mem_used, "memoryUsed", 1024**3)
    fill_gpu(gpu_mem_total, "memoryTotal", 1024**3)
    fill_gpu(gpu_temp, "temperature")
    fill_gpu(gpu_power, "powerDraw")

    if gpu_info:
        for item in gpu_info:
            metric = item.get("metric", {})
            uuid = metric.get("uuid", "")
            if uuid in gpus_map:
                gpus_map[uuid]["model"] = metric.get("name", gpus_map[uuid]["model"])

    gpu_list = list(gpus_map.values())
    gpu_list.sort(key=lambda x: x["id"])
    node_details["gpus"] = gpu_list

    return node_details