#!/bin/sh
set -eu
image=${1:-math-practice-tutor:ci}
volume="math-tutor-ci-$$"
api_name="math-tutor-api-$$"
worker_name="math-tutor-worker-$$"
cleanup() {
  docker rm -f "$api_name" "$worker_name" >/dev/null 2>&1 || :
  docker volume rm "$volume" >/dev/null 2>&1 || :
}
trap cleanup EXIT HUP INT TERM
docker volume create "$volume" >/dev/null
docker run --rm --read-only --tmpfs /tmp "$image" python -c 'import importlib.util; from io import BytesIO; from PIL import Image; from math_tutor.adapters.images import normalize; from cryptography.hazmat.primitives.ciphers.aead import AESGCM; output=BytesIO(); Image.new("RGB",(64,32),"white").save(output,format="HEIF"); normalized=normalize(output.getvalue()); assert Image.open(BytesIO(normalized)).format=="JPEG"; assert len(AESGCM.generate_key(bit_length=256))==32; assert importlib.util.find_spec("pip") is None; assert importlib.util.find_spec("setuptools") is None; print("HEIF normalization, cryptography, and installer-free runtime passed.")'
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges "$image" python -c '
from uuid import uuid4
from math_tutor.adapters.providers.config import ProviderConfig
from math_tutor.adapters.providers.contracts import ModelRequest, ProviderError
from math_tutor.providers import complete
config = ProviderConfig(adapter="compatible", model="synthetic-disabled-v1")
request = ModelRequest(operation_id=uuid4(), stage="tutor", model_id=config.model,
    system_instruction="Synthetic process check", ordered_messages=[], response_schema={},
    timeout_seconds=5)
try:
    complete(config, request)
except ProviderError as error:
    assert error.code == "configuration_mismatch", error.code
else:
    raise AssertionError("A disabled provider must reject before any network call")
print("Restricted container provider subprocess and typed failure passed; no inference.")
'
docker run --rm --user 0:0 --mount "type=volume,src=$volume,dst=/app/data" "$image" python -c 'import os; os.chown("/app/data",10001,10001); os.chmod("/app/data",0o700)'
secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
export SESSION_SECRET="$secret"
export APP_PUBLIC_ORIGIN=http://127.0.0.1:18080
docker run --rm --mount "type=volume,src=$volume,dst=/app/data" --env SESSION_SECRET --env APP_PUBLIC_ORIGIN "$image" alembic -c alembic.ini upgrade head
docker run --rm --mount "type=volume,src=$volume,dst=/app/data" "$image" python -m math_tutor.cli db
docker run -d --name "$api_name" --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --mount "type=volume,src=$volume,dst=/app/data" --env SESSION_SECRET --env APP_PUBLIC_ORIGIN --env SHEPHERD_OWNER_SOCKET=/tmp/shepherd-owner/setup.sock -p 127.0.0.1:18080:8000 "$image" >/dev/null
docker run -d --name "$worker_name" --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --mount "type=volume,src=$volume,dst=/app/data" --env SESSION_SECRET --env APP_PUBLIC_ORIGIN "$image" python -m math_tutor.worker >/dev/null
python3 - "$api_name" <<'PY'
import http.cookiejar,json,subprocess,sys,time,urllib.error,urllib.request
for attempt in range(30):
 try:
  with urllib.request.urlopen('http://127.0.0.1:18080/health/ready',timeout=2) as response:
   assert json.load(response)=={'status':'ready'}
  with urllib.request.urlopen('http://127.0.0.1:18080/') as response:assert b'Shepherd Academy Universe' in response.read()
  break
 except OSError:
  time.sleep(1)
else:raise SystemExit('Container startup failed.')
print('Non-root container, SQLite migration, worker readiness, and built UI passed.')

def owner_link():
 result=subprocess.run(['docker','exec',sys.argv[1],'python','-m','math_tutor.owner_setup'],capture_output=True,text=True,timeout=15)
 assert result.returncode==0, 'Owner command failed.'
 return result.stdout

old_token=owner_link().split('#setup=')[1].strip()
new_token=owner_link().split('#setup=')[1].strip()
assert old_token!=new_token, 'Setup renewal must replace the previous link.'
origin='http://127.0.0.1:18080'
browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
with browser.open(origin+'/api/v1/auth/session',timeout=5) as response:
 csrf=json.load(response)['csrf_token']
headers={'Content-Type':'application/json','Origin':origin,'X-CSRF-Token':csrf}
def exchange(token):
 body=json.dumps({'setup_token':token}).encode()
 return browser.open(urllib.request.Request(origin+'/api/v1/auth/setup/session',data=body,headers=headers),timeout=10)
try:
 with exchange(old_token):
  raise AssertionError('Replaced owner link was accepted.')
except urllib.error.HTTPError as error:
 assert error.code==403, 'Expected stale-link rejection.'
with exchange(new_token) as response:
 assert json.load(response)['available'] is True
with browser.open(origin+'/api/v1/auth/setup',timeout=5) as response:
 assert json.load(response)['available'] is True
body=json.dumps({'login_name':'synthetic-owner','password':'plain6','password_confirmation':'plain6'}).encode()
with browser.open(urllib.request.Request(origin+'/api/v1/auth/setup',data=body,headers=headers),timeout=10) as response:
 assert json.load(response)['authenticated'] is True
assert '#setup=' not in owner_link(), 'Claimed accounts must not receive setup authority.'
print('Container owner-link renewal, stale-link rejection, browser account creation and claimed-account protection passed.')
PY
