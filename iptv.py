import requests
from bs4 import BeautifulSoup
import re

def get_online_address_map(url):
    """
    从指定的网页爬取频道名称和组播地址的对应关系
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    address_map = {}
    
    try:
        print(f"正在从 {url} 获取数据...")
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8' # 确保中文不乱码
        
        if response.status_code != 200:
            print(f"网页请求失败，状态码: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        # 寻找网页中的表格
        table = soup.find('table')
        if not table:
            print("未在网页中找到数据表格")
            return None

        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            # 根据网页结构：通常第2列是名称，第3列是地址
            if len(cols) >= 3:
                name = cols[1].get_text(strip=True)
                address = cols[2].get_text(strip=True)
                
                # 过滤掉表头
                if "频道名称" not in name and "组播地址" not in address:
                    address_map[name] = address

        print(f"数据爬取完成，共提取到 {len(address_map)} 个频道。")
        print(address_map)
        return address_map

    except Exception as e:
        print(f"爬取过程中出现错误: {e}")
        return None

def update_m3u_with_online_data(m3u_path, output_path, target_url):
    # 1. 获取在线最新的地址映射
    address_map = get_online_address_map(target_url)
    if not address_map:
        print("无法获取在线数据，更新终止。")
        return

    # 2. 读取并处理本地 M3U 文件
    final_content = []
    try:
        with open(m3u_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 匹配 #EXTINF 行
            if line.startswith("#EXTINF"):
                # 获取频道名（逗号后的文字）
                if "," in line:
                    channel_name = line.split(",")[-1].strip()
                    
                    # 检查下一行是否是地址行
                    if i + 1 < len(lines):
                        url_line = lines[i+1].strip()
                        
                        # 如果地址中包含 /rtp/ 且匹配到在线新地址
                        if "/rtp/" in url_line and channel_name in address_map:
                            new_addr = address_map[channel_name]
                            
                            # 修复之前出现的 S9 乱码问题：使用 split 拼接
                            prefix = url_line.split("/rtp/")[0] + "/rtp/"
                            new_url = prefix + new_addr
                            
                            final_content.append(lines[i])      # 保留 EXTINF 行
                            final_content.append(new_url + "\n") # 写入新地址
                            i += 2
                            continue
            
            # 无需替换的行原样保留
            final_content.append(lines[i])
            i += 1

        # 3. 保存新文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(final_content)
        print(f"成功！最新 M3U 已生成: {output_path}")

    except Exception as e:
        print(f"处理 M3U 文件时出错: {e}")

# 执行逻辑
if __name__ == "__main__":
    TARGET_URL = "https://epg.51zmt.top:8001/sctvmulticast.html"
    INPUT_M3U = "2.m3u"        # 你的原始文件
    OUTPUT_M3U = "2.m3u" # 生成的结果文件
    
    update_m3u_with_online_data(INPUT_M3U, OUTPUT_M3U, TARGET_URL)