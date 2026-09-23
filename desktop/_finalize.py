"""定稿流水线：停掉正在运行的桌面版 → 构建前端 → 部署 → 重新打包 → 重新拉起桌面版。

必须按序：桌面版正从 dist/win-unpacked 运行，文件被占用会导致打包失败。
"""
import os
import subprocess
import time
import urllib.request

R = r'C:/Users/wszy1/WorkBuddy/2026-09-18-01-07-46/inkrealm'
PY = r'C:/Users/wszy1/.workbuddy/binaries/python/versions/3.13.12/python.exe'
NODE = r'C:/Users/wszy1/.workbuddy/binaries/node/versions/22.22.2-3/node.exe'
EXE = os.path.join(R, 'desktop', 'dist', 'win-unpacked', '万维文 WitWork.exe')


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', **kw)


def listening_pid(port=8723):
    out = sh(['cmd.exe', '/c', 'netstat', '-ano']).stdout or ''
    for l in out.splitlines():
        if ':%d' % port in l and 'LISTENING' in l.upper():
            return l.split()[-1]
    return None


def stop_app():
    sh(['cmd.exe', '/c', 'taskkill', '/F', '/IM', '万维文 WitWork.exe'])
    time.sleep(2)
    pid = listening_pid()
    if pid:
        sh(['cmd.exe', '/c', 'taskkill', '/F', '/PID', pid])
        time.sleep(1)
    print('  已停桌面版；8723 监听:', listening_pid() or '无')


def build_deploy():
    p = subprocess.run([PY, os.path.join(R, 'web-astro', '_build_once.py'), '240', '2'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('  构建:', (p.stdout or '').strip()[-120:])
    # 关键：构建失败必须中止，否则会把旧 dist 当成新版部署+打包（曾因此误判"改动没生效"）
    if p.returncode != 0:
        raise SystemExit('构建失败，已中止后续部署与打包（去看 web-astro/build_once.txt）')
    p = sh([PY, os.path.join(R, 'web-astro', 'deploy_astro.py')])
    print('  部署:', (p.stdout or '').strip()[-80:])


def repack():
    env = dict(os.environ)
    env.pop('ELECTRON_RUN_AS_NODE', None)
    env.pop('NODE_OPTIONS', None)          # 否则 harness 的 node shim 会拦截 electron-builder 的删除
    env['CSC_IDENTITY_AUTO_DISCOVERY'] = 'false'
    # winCodeSign（内含 rcedit，嵌入 exe 图标必需）：国内直连 GitHub 会卡死，
    # 优先走 npmmirror 镜像；若镜像也挂，可手动把缓存补成 Cache\winCodeSign\winCodeSign-2.6.0
    env.setdefault('ELECTRON_BUILDER_BINARIES_MIRROR',
                   'https://npmmirror.com/mirrors/electron-builder-binaries/')
    log_path = os.path.join(R, 'desktop', 'pack_log.txt')
    with open(log_path, 'w', encoding='utf-8', errors='replace') as f:
        f.write('--- electron-builder --dir --win ---\n')
        f.flush()
        p = subprocess.run([NODE, 'node_modules/electron-builder/cli.js', '--dir', '--win', '--publish', 'never'],
                           cwd=os.path.join(R, 'desktop'), env=env,
                           stdout=f, stderr=subprocess.STDOUT, timeout=900)
    tail = [l for l in open(log_path, encoding='utf-8', errors='replace').read().splitlines()
            if 'packaging' in l or 'error' in l.lower() or 'cannot' in l.lower()]
    print('  打包 rc=%s（全量日志: %s）' % (p.returncode, log_path))
    for l in tail[-3:]:
        print('    ', l.strip()[:140])


def launch():
    env = dict(os.environ)
    env.pop('ELECTRON_RUN_AS_NODE', None)
    env.pop('NODE_OPTIONS', None)
    env.pop('INKREALM_SHOT', None)
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([EXE], env=env, creationflags=flags, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(1)
        try:
            r = urllib.request.urlopen('http://127.0.0.1:8723/api/health', timeout=2)
            print('  桌面版已启动，后端健康:', r.status)
            return True
        except Exception:
            pass
    print('  启动后 30s 内后端未就绪')
    return False


if __name__ == '__main__':
    print('1) 停掉正在运行的桌面版'); stop_app()
    print('2) 构建 + 部署前端'); build_deploy()
    print('3) 重新打包'); repack()
    print('4) 重新拉起桌面版'); launch()
    print('DONE')
