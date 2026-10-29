"""Ejecuta suites aisladas en procesos distintos, sin compartir SQLite ni mocks."""
import concurrent.futures,pathlib,re,subprocess,sys

ROOT=pathlib.Path(__file__).resolve().parent.parent

def run(path):
 result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',path.name,'-v'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 output=result.stdout.decode('utf8',errors='replace');counts=re.findall(r'Ran (\d+) tests? in',output)
 return path.name,result.returncode,int(counts[-1]) if counts else 0,output

if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf8',errors='replace')
 paths=sorted((ROOT/'tests').glob('test_*.py'));failures=[];total=0
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for name,code,count,output in pool.map(run,paths):
   total+=count;print(f'{name}: {count} pruebas · '+('ERROR' if code else 'OK'),flush=True)
   if code:failures.append(name);print(output,flush=True)
 print(f'TOTAL: {total} pruebas en {len(paths)} suites; fallidas: {len(failures)}.',flush=True)
 sys.exit(1 if failures or not total else 0)
