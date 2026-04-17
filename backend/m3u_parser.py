"""
M3U Parser and Channel Processor
Handles M3U file parsing, encoding detection, and channel extraction
"""
import re
import chardet
from typing import List, Dict, Optional
from datetime import datetime


def detect_encoding(file_path: str) -> str:
    """Detect file encoding"""
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000)  # Read first 10KB
    result = chardet.detect(raw_data)
    return result['encoding'] or 'utf-8'


def parse_m3u_file(file_path: str) -> List[Dict]:
    """
    Parse M3U file and extract channel information
    Returns list of channel dicts
    """
    # Try UTF-8 first, then detect
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030']
    content = None

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        # Fallback to detection
        encoding = detect_encoding(file_path)
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()

    return parse_m3u_content(content)


def parse_m3u_content(content: str) -> List[Dict]:
    """Parse M3U content string"""
    channels = []
    lines = content.strip().split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith('#EXTINF:'):
            # Parse EXTINF line
            channel = parse_extinf_line(line)

            # Next line should be the URL
            i += 1
            if i < len(lines):
                url = lines[i].strip()
                if url and not url.startswith('#'):
                    channel['live_url'] = url
                    channels.append(channel)
        i += 1

    return channels


def parse_extinf_line(line: str) -> Dict:
    """Parse #EXTINF line"""
    channel = {
        'tvg_name': '',
        'tvg_logo': '',
        'group_title': '',
        'catchup_type': '',
        'catchup_source': '',
    }

    # Extract tvg-name
    match = re.search(r'tvg-name="([^"]*)"', line)
    if match:
        channel['tvg_name'] = match.group(1)

    # Extract tvg-logo
    match = re.search(r'tvg-logo="([^"]*)"', line)
    if match:
        channel['tvg_logo'] = match.group(1)

    # Extract group-title
    match = re.search(r'group-title="([^"]*)"', line)
    if match:
        channel['group_title'] = match.group(1)

    # Extract catchup-source
    match = re.search(r'catchup-source="([^"]*)"', line)
    if match:
        channel['catchup_source'] = match.group(1)

    # Extract catchup
    match = re.search(r'catchup="([^"]*)"', line)
    if match:
        channel['catchup_type'] = match.group(1)

    # Extract channel name (after comma)
    if ',' in line:
        name = line.split(',')[-1].strip()
        if not channel['tvg_name']:
            channel['tvg_name'] = name

    return channel


def generate_m3u_content(
    channels: List[Dict],
    use_catchup: bool = True,
    rtp_prefix: str = "http://192.168.10.1:10000/rtp/"
) -> str:
    """
    Generate M3U content from channel list
    """
    lines = ['#EXTM3U']

    for ch in channels:
        # Build EXTINF line
        attrs = []

        if ch.get('tvg_name'):
            attrs.append(f'tvg-name="{ch["tvg_name"]}"')

        if ch.get('tvg_logo'):
            attrs.append(f'tvg-logo="{ch["tvg_logo"]}"')

        if ch.get('group_title'):
            attrs.append(f'group-title="{ch["group_title"]}"')

        # Handle catchup
        catchup_source = ch.get('catchup_source', '')
        if use_catchup and catchup_source:
            attrs.append(f'catchup-source="{catchup_source}"')
            attrs.append('catchup="append"')

        name = ch.get('custom_name') or ch.get('tvg_name') or 'Unknown'
        extinf_line = f'#EXTINF:-1 {",".join(attrs)},{name}'
        lines.append(extinf_line)

        # Process URL - apply RTP prefix if needed
        url = ch.get('live_url', '')
        if url and not url.startswith('http'):
            url = rtp_prefix + url

        lines.append(url)

    return '\n'.join(lines)


def match_catchup_template(url: str) -> Optional[Dict]:
    """
    Detect if URL matches known catchup patterns
    Returns {catchup_type, catchup_source_template}
    """
    # Common catchup patterns
    patterns = [
        # RTSP pattern
        (r'rtsp://.*/PLTV/(\d+)/', {
            'type': 'append',
            'template': 'rtsp://{ip}/PLTV/{id}/play.html?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}'
        }),
        # HTTP pattern
        (r'http://.*/(\d+)\.m3u8?', {
            'type': 'append',
            'template': 'http://{host}/${id}.m3u8?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}'
        }),
    ]

    for pattern, template in patterns:
        match = re.search(pattern, url)
        if match:
            return {
                'catchup_type': template['type'],
                'catchup_source': template['template']
            }

    return None
