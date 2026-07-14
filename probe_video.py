import subprocess, json, os
r = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', r'E:\YifuAIForge\OpenMontage\fabric-showcase-silk\renders\fabric_showcase.mp4'],
    capture_output=True, text=True, encoding='utf-8', errors='replace')
try:
    data = json.loads(r.stdout)
    for s in data.get('streams', []):
        print(json.dumps(s, indent=2))
except Exception as e:
    print(f"Error: {e}")
    print("stdout:", r.stdout[:500])
    print("stderr:", r.stderr[:500])
