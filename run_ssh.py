import sys
sys.stdout.reconfigure(encoding='utf-8')
import paramiko

def execute_remote(cmd: str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('13.140.146.163', port=22, username='root', password='7DoGpDwZ4zpIvotZm9p', timeout=15)
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    client.close()
    return out, err

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
    else:
        cmd = "uname -a"
    out, err = execute_remote(cmd)
    if out:
        print(out)
    if err:
        print("STDERR:", err)
