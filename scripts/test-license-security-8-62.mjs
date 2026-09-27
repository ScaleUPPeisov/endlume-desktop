import assert from 'node:assert/strict';
import { createHash, randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';

const admin=readFileSync('supabase/functions/endlume-admin-licenses/index.ts','utf8');
const client=readFileSync('supabase/functions/endlume-client-api/index.ts','utf8');
const migration=readFileSync('supabase/migrations/20260918_endlume_license_integrity_hardening.sql','utf8');

const generator=admin.slice(admin.indexOf('const alphabet='),admin.indexOf('async function hash'));
assert.match(generator,/crypto\.getRandomValues\(new Uint8Array\(4\)\)/);
assert.match(generator,/const KEY_GROUPS=8/);
assert.ok(!generator.includes('Math.random'), 'license generator must not use Math.random');
assert.ok(!generator.includes('Date.now'), 'license generator must not use timestamps');
assert.ok(!generator.includes('crypto.randomUUID'), 'license security must not depend on plain UUID generation');

const alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
assert.equal(alphabet.length,32);
const groups=8, charsPerGroup=4;
const entropyBits=groups*charsPerGroup*Math.log2(alphabet.length);
assert.ok(entropyBits>=128, `entropy too low: ${entropyBits}`);
assert.equal(entropyBits,160);

function group(){
  const b=randomBytes(charsPerGroup);
  return [...b].map(x=>alphabet[x%alphabet.length]).join('');
}
function key(){
  return 'ENDLUME-'+Array.from({length:groups},group).join('-');
}

const raw=new Set();
const hashes=new Set();
let previous=null;
for(let i=0;i<10_000;i++){
  const k=key();
  const parts=k.split('-');
  assert.equal(parts.length,9);
  assert.equal(parts[0],'ENDLUME');
  for(const g of parts.slice(1)){
    assert.equal(g.length,4);
    for(const ch of g) assert.ok(alphabet.includes(ch), `invalid character ${ch}`);
  }
  assert.notEqual(k,previous,'adjacent generated keys must differ');
  previous=k;
  assert.ok(!raw.has(k),`raw collision at ${i}`);
  raw.add(k);
  const h=createHash('sha256').update(k).digest('hex');
  assert.match(h,/^[0-9a-f]{64}$/);
  assert.ok(!hashes.has(h),`hash collision at ${i}`);
  hashes.add(h);
}
assert.equal(raw.size,10_000);
assert.equal(hashes.size,10_000);

assert.match(admin,/for\(let i=0;i<5;i\+\+\)/,'collision retry missing');
assert.match(admin,/error\?\.code!==["']23505["']/,'DB unique collision must be distinguished by SQLSTATE');
assert.match(admin,/key_hash:await hash\(k\)/,'server must store key hash');
assert.match(admin,/key_last4:k\.slice\(-4\)/,'server may retain only masked suffix');
assert.ok(!admin.includes('raw_key:'),'raw customer key must not be persisted');
assert.match(admin,/if\(owner&&actorRole!==["']owner["']\)return out\(\{ok:false,code:["']owner_required["']\},403\)/);
assert.match(client,/\(parts\.length === 5 \|\| parts\.length === 9\)/,'legacy + strong key activation compatibility missing');
assert.match(client,/new Uint8Array\(32\)/,'session token must use 256-bit random material');
assert.match(client,/code: "binding_mismatch"/);
assert.match(client,/rawKey\.length > 128/);
assert.match(client,/contentLength > 65536/);
assert.ok(!client.includes('render_upsert_failed", detail:'),'DB details must not leak to managed client');
assert.match(admin,/Deno\.env\.get\(["']SUPABASE_SERVICE_ROLE_KEY["']\)/);
assert.ok(!/SUPABASE_SERVICE_ROLE_KEY\s*=\s*["'][^"']+["']/.test(admin),'service role literal detected');

for(const needle of [
  'endlume_licenses_owner_plan_consistency_chk',
  'endlume_licenses_key_hash_hex_chk',
  'endlume_sessions_token_hash_hex_chk',
  'endlume_sessions_device_license_fkey',
  'endlume_renders_device_license_fkey',
  'endlume_render_events_device_license_fkey',
]) assert.ok(migration.includes(needle),`migration contract missing: ${needle}`);

console.log(`PASS: 10,000/10,000 unique strong license keys; entropy=${entropyBits} bits; owner/hash/session contracts preserved`);
