from flask import Flask, jsonify, request, send_from_directory
import os
import sys
import time
import re
from datetime import datetime

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# 导入现有的iptv模块
from iptv import process_m3u

# 设置M3U_FILE路径，指向项目根目录下的2.m3u
M3U_FILE = os.path.join(project_root, '2.m3u')

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# 提供静态文件和index.html
@app.route('/')
def index():
    # 获取项目根目录
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return send_from_directory(root_dir, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    # 获取项目根目录
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return send_from_directory(root_dir, path)

# 全局变量用于存储日志
logs = []

def log_message(message):
    """记录日志信息"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    logs.append(log_entry)
    # 限制日志数量，只保留最近100条
    if len(logs) > 100:
        logs.pop(0)
    print(log_entry)

@app.route('/api/m3u/info', methods=['GET'])
def get_m3u_info():
    """获取M3U文件信息"""
    try:
        if os.path.exists(M3U_FILE):
            file_stat = os.stat(M3U_FILE)
            file_size = file_stat.st_size
            modified_time = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            return jsonify({
                'status': 'success',
                'data': {
                    'file_path': M3U_FILE,
                    'file_size': file_size,
                    'modified_time': modified_time,
                    'exists': True
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'文件 {M3U_FILE} 不存在',
                'data': {
                    'exists': False
                }
            })
    except Exception as e:
        log_message(f"获取M3U文件信息失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'获取M3U文件信息失败: {e}'
        })

@app.route('/api/m3u/update', methods=['POST'])
def update_m3u():
    """更新M3U文件"""
    try:
        # 清空之前的日志
        logs.clear()
        log_message("开始更新M3U文件...")
        
        # 执行更新
        process_m3u()
        
        log_message("M3U文件更新完成")
        
        return jsonify({
            'status': 'success',
            'message': 'M3U文件更新成功',
            'logs': logs
        })
    except Exception as e:
        error_message = f"更新M3U文件失败: {e}"
        log_message(error_message)
        return jsonify({
            'status': 'error',
            'message': error_message
        })

@app.route('/api/m3u/upload', methods=['POST'])
def upload_m3u():
    """上传M3U文件"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'status': 'error',
                'message': '没有文件部分'
            })
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'status': 'error',
                'message': '没有选择文件'
            })
        
        # 检查文件扩展名
        if file and (file.filename.endswith('.m3u') or file.filename.endswith('.m3u8')):
            # 保存文件到项目根目录，命名为2.m3u
            file.save(M3U_FILE)
            log_message(f"M3U文件上传成功: {file.filename}")
            return jsonify({
                'status': 'success',
                'message': 'M3U文件上传成功',
                'data': {
                    'filename': file.filename,
                    'file_path': M3U_FILE
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '只允许上传.m3u或.m3u8文件'
            })
    except Exception as e:
        error_message = f"上传M3U文件失败: {e}"
        log_message(error_message)
        return jsonify({
            'status': 'error',
            'message': error_message
        })

@app.route('/api/m3u/url', methods=['GET'])
def get_m3u_url():
    """获取M3U文件的访问地址"""
    try:
        # 获取M3U文件名，只返回相对路径
        m3u_filename = os.path.basename(M3U_FILE)
        base_url = request.host_url
        m3u_url = f"{base_url}{m3u_filename}"
        
        return jsonify({
            'status': 'success',
            'message': '获取M3U地址成功',
            'data': {
                'm3u_url': m3u_url
            }
        })
    except Exception as e:
        log_message(f"生成M3U文件地址失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'生成M3U文件地址失败: {e}'
        })

@app.route('/api/m3u/check', methods=['GET'])
def check_m3u_url():
    """检测M3U地址有效性"""
    try:
        # 获取M3U文件名，只返回相对路径
        m3u_filename = os.path.basename(M3U_FILE)
        base_url = request.host_url
        m3u_url = f"{base_url}{m3u_filename}"
        
        # 尝试访问M3U文件
        import requests
        response = requests.get(m3u_url, timeout=10)
        
        if response.status_code == 200:
            # 检查文件内容是否为M3U格式
            content = response.text
            if content.startswith('#EXTM3U'):
                return jsonify({
                    'status': 'success',
                    'message': 'M3U地址有效',
                    'data': {
                        'm3u_url': m3u_url,
                        'status_code': response.status_code,
                        'is_valid': True
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'M3U文件格式无效',
                    'data': {
                        'm3u_url': m3u_url,
                        'status_code': response.status_code,
                        'is_valid': False
                    }
                })
        else:
            return jsonify({
                'status': 'error',
                'message': f'M3U地址访问失败，状态码: {response.status_code}',
                'data': {
                    'm3u_url': m3u_url,
                    'status_code': response.status_code,
                    'is_valid': False
                }
            })
    except Exception as e:
        log_message(f"检测M3U地址有效性失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'检测M3U地址有效性失败: {e}',
            'data': {
                'is_valid': False
            }
        })

@app.route('/api/channels', methods=['GET'])
def get_channels():
    """获取频道列表"""
    try:
        if not os.path.exists(M3U_FILE):
            return jsonify({
                'status': 'error',
                'message': f'文件 {M3U_FILE} 不存在'
            })
        
        # 解析M3U文件
        channels = []
        with open(M3U_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXTINF'):
                # 解析频道信息
                name = line.split(',')[-1].strip()
                url = lines[i+1].strip() if i+1 < len(lines) else ""
                
                # 提取分组信息
                group_match = re.search(r'group-title="([^"]*)"', line)
                group = group_match.group(1) if group_match else "未分组"
                
                # 提取tvg-name信息
                tvg_match = re.search(r'tvg-name="([^"]*)"', line)
                tvg_name = tvg_match.group(1) if tvg_match else name
                
                # 提取catchup-source信息
                catchup_match = re.search(r'catchup-source="([^"]*)"', line)
                catchup_source = catchup_match.group(1) if catchup_match else ""
                
                # 模拟频道状态（50%在线，50%离线）
                status = "online" if hash(name) % 2 == 0 else "offline"
                
                # 生成一个简单的logo URL
                logo = f"https://example.com/{name.replace(' ', '_').lower()}.png"
                
                channels.append({
                    'id': i,
                    'name': name,
                    'tvg_name': tvg_name,
                    'url': url,
                    'group': group,
                    'catchup_source': catchup_source,
                    'logo': logo,
                    'status': status
                })
                i += 2
            else:
                i += 1
        
        return jsonify({
            'status': 'success',
            'message': '获取频道列表成功',
            'data': {
                'channels': channels,
                'total': len(channels)
            }
        })
    except Exception as e:
        log_message(f"获取频道列表失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'获取频道列表失败: {e}'
        })

@app.route('/api/channel/<int:channel_id>/check', methods=['GET'])
def check_channel(channel_id):
    """检测单个频道的有效性"""
    try:
        if not os.path.exists(M3U_FILE):
            return jsonify({
                'status': 'error',
                'message': f'文件 {M3U_FILE} 不存在'
            })
        
        # 解析M3U文件，查找指定ID的频道
        with open(M3U_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        i = 0
        channel_url = None
        channel_name = None
        
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXTINF') and i == channel_id:
                # 找到指定ID的频道
                channel_name = line.split(',')[-1].strip()
                channel_url = lines[i+1].strip() if i+1 < len(lines) else ""
                break
            if line.startswith('#EXTINF'):
                i += 2
            else:
                i += 1
        
        if not channel_url:
            return jsonify({
                'status': 'error',
                'message': f'未找到ID为 {channel_id} 的频道'
            })
        
        # 检测频道URL的有效性
        import requests
        import time
        
        try:
            start_time = time.time()
            response = requests.get(channel_url, timeout=5, stream=True)
            response.close()
            latency = int((time.time() - start_time) * 1000)
            
            if response.status_code >= 200 and response.status_code < 300:
                return jsonify({
                    'status': 'success',
                    'message': '频道有效',
                    'data': {
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'url': channel_url,
                        'is_valid': True,
                        'status_code': response.status_code,
                        'latency': latency,
                        'status': 'online'
                    }
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'频道访问失败，状态码: {response.status_code}',
                    'data': {
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'url': channel_url,
                        'is_valid': False,
                        'status_code': response.status_code,
                        'status': 'offline'
                    }
                })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'频道检测失败: {e}',
                'data': {
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'url': channel_url,
                    'is_valid': False,
                    'status': 'offline'
                }
            })
    except Exception as e:
        log_message(f"检测频道失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'检测频道失败: {e}'
        })

@app.route('/api/m3u/generate', methods=['POST'])
def generate_m3u():
    """生成选中频道的M3U文件"""
    try:
        if not os.path.exists(M3U_FILE):
            return jsonify({
                'status': 'error',
                'message': f'文件 {M3U_FILE} 不存在'
            })
        
        # 获取请求数据
        data = request.get_json()
        selected_channel_ids = data.get('channel_ids', [])
        
        if not selected_channel_ids:
            return jsonify({
                'status': 'error',
                'message': '请选择至少一个频道'
            })
        
        # 解析M3U文件，提取选中频道的信息
        with open(M3U_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 生成新的M3U内容
        m3u_content = '#EXTM3U\n'
        selected_count = 0
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('#EXTINF'):
                # 检查当前频道ID是否在选中列表中
                if str(i) in map(str, selected_channel_ids) or i in selected_channel_ids:
                    # 提取频道信息
                    m3u_content += line + '\n'
                    if i+1 < len(lines):
                        m3u_content += lines[i+1]
                    selected_count += 1
                i += 2
            else:
                i += 1
        
        # 生成临时M3U文件
        import uuid
        temp_m3u_file = os.path.join(project_root, f'temp_{uuid.uuid4().hex}.m3u')
        with open(temp_m3u_file, 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        
        # 获取M3U文件的访问URL
        base_url = request.host_url
        temp_m3u_filename = os.path.basename(temp_m3u_file)
        m3u_url = f"{base_url}{temp_m3u_filename}"
        
        return jsonify({
            'status': 'success',
            'message': f'成功生成 {selected_count} 个频道的M3U文件',
            'data': {
                'm3u_url': m3u_url,
                'temp_file': temp_m3u_filename,
                'selected_count': selected_count,
                'content': m3u_content
            }
        })
    except Exception as e:
        log_message(f"生成M3U文件失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'生成M3U文件失败: {e}'
        })

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """获取日志信息"""
    return jsonify({
        'status': 'success',
        'data': {
            'logs': logs
        }
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)