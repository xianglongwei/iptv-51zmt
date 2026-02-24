import requests
import re
import os

# --- 配置区 ---
# 根据截图确认的 API 地址
API_URL = "https://epg.51zmt.top:8001/multicast/api/channels/1/"
M3U_FILE = "2.m3u"
# 你的局域网转发前缀
RTP_PREFIX = "http://192.168.10.1:10000/rtp/"
# 必填的回放时间参数
PLAYSEEK_PARAM = "?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}"

def get_online_data():
    """从 API 获取 JSON 数据并转换格式"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://epg.51zmt.top:8001/multicast/'
    }
    try:
        response = requests.get(API_URL, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json().get('channels', [])
    except Exception as e:
        print(f"API 请求失败: {e}")
    return []

def process_m3u():
    online_list = get_online_data()
    if not online_list:
        return

    if not os.path.exists(M3U_FILE):
        print(f"错误: 找不到文件 {M3U_FILE}")
        return

    # 1. 解析本地 M3U 文件
    with open(M3U_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    m3u_items = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            name = line.split(",")[-1].strip()
            url = lines[i+1].strip() if i+1 < len(lines) else ""
            m3u_items.append({"info": line, "url": url, "name": name})
            i += 2
        else:
            if line and not line.startswith("#EXTM3U"):
                m3u_items.append({"raw": lines[i]})
            i += 1

    # 2. 处理在线频道（更新或新增）
    for online in online_list:
        o_name = online['channel_name'].strip()
        o_addr = online['multicast_address'].strip()
        # 提取 replay_url 字段
        o_replay = online.get('replay_url', '').strip()
        
        # 构造完整的回放地址
        if o_replay and PLAYSEEK_PARAM not in o_replay:
            o_replay += PLAYSEEK_PARAM
        
        new_url = f"{RTP_PREFIX}{o_addr}"
        
        # 查找 M3U 是否已存在该频道
        match = next((item for item in m3u_items if item.get("name") == o_name), None)
        
        if match:
            # 更新已有频道
            match["url"] = new_url
            # 更新 info 行中的回放地址
            if o_replay:
                if 'catchup-source="' in match["info"]:
                    match["info"] = re.sub(r'catchup-source="[^"]*"', f'catchup-source="{o_replay}"', match["info"])
                else:
                    match["info"] = match["info"].replace(f",{o_name}", f' catchup-source="{o_replay}",{o_name}')
            print(f"【已更新】 {o_name}")
            
        elif "4K" in o_name or "UHD" in o_name:
            # 如果是新 4K 频道，执行插入逻辑
            # 基础名匹配（例如通过 "四川卫视" 找 "四川卫视高清" 的位置）
            base_name = o_name.replace("4K", "").replace("UHD", "").strip()
            
            # 寻找插入位置（邻居模式）
            insert_pos = -1
            for idx, item in enumerate(m3u_items):
                if item.get("name") and base_name in item["name"]:
                    insert_pos = idx
            
            new_info = f'#EXTINF:-1 tvg-name="{o_name}" group-title="卫视" catchup-source="{o_replay}",{o_name}'
            new_entry = {"info": new_info, "url": new_url, "name": o_name}
            
            if insert_pos != -1:
                m3u_items.insert(insert_pos + 1, new_entry)
                print(f"【已插入】 {o_name} (紧跟 {m3u_items[insert_pos]['name']})")
            else:
                m3u_items.append(new_entry)
                print(f"【已添加】 {o_name} (末尾)")

    # 3. 写入文件
    with open(M3U_FILE, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for item in m3u_items:
            if "raw" in item:
                f.write(item["raw"])
            else:
                f.write(item["info"] + "\n")
                f.write(item["url"] + "\n")
    print("\n所有操作已完成。")

if __name__ == "__main__":
    process_m3u()
