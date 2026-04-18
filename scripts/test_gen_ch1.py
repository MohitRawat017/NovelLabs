import httpx, time, sys

API = 'http://localhost:8001/api'
SLUG = 'the-100th-regression-of-the-max-level-player'
CH = 1

print(f'Triggering generation: {SLUG} chapter {CH}...')
with httpx.Client(timeout=120) as client:
    r = client.post(f'{API}/audio/generate/{SLUG}/{CH}', params={'voice': 'bm_george', 'provider': 'kokoro'})
    print(f'Response: {r.status_code}')
    print(r.text[:300])

    if r.status_code not in (200, 202):
        sys.exit(1)

    data = r.json()
    if data.get('status') == 'exists':
        print('[SKIPPED] Already generated.')
        sys.exit(0)

    print('Polling for completion...')
    for _ in range(300):
        time.sleep(3)
        s = client.get(f'{API}/audio/status/{SLUG}/{CH}')
        if s.status_code == 200:
            sd = s.json()
            js = sd.get('job_status')
            prog = sd.get('progress', 0)
            print(f'  status={js} progress={prog}%')
            if js == 'completed':
                print('[OK] Chapter 1 audio generated successfully!')
                sys.exit(0)
            elif js in ('failed', 'cancelled'):
                msg = sd.get('message')
                print(f'[FAILED] {msg}')
                sys.exit(1)
        else:
            print(f'[WARN] Status check returned {s.status_code}')
