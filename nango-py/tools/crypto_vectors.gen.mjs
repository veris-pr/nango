// Emits crypto parity vectors for the nango-py auth adapter.
//
// Replicates the authoritative TypeScript algorithms directly from node:crypto:
//   - PBKDF2-HMAC-SHA256, 310000 iterations, 32 bytes, base64 (secret_service/customerKey hashing)
//     Mirrors packages/keystore/lib/utils/encryption.ts and packages/shared/lib/utils/encryption.manager.ts
//   - AES-256-GCM, 12-byte iv, 16-byte auth tag, base64 (api_secrets / connection credential encryption)
//     Mirrors packages/utils/lib/encryption.ts Encryption.encryptSync/decryptSync
//
// Run from the repository root:
//   node nango-py/tools/crypto_vectors.gen.mjs
//
// Output: nango-py/tests/contract/fixtures/crypto/parity_vectors.json
// The Python parity test consumes this file. Re-generate when the TS algorithm changes.

import crypto from 'node:crypto';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const outPath = resolve(here, '../tests/contract/fixtures/crypto/parity_vectors.json');

function pbkdf2Hash(plaintext, encryptionKey) {
    return crypto.pbkdf2Sync(plaintext, encryptionKey, 310000, 32, 'sha256').toString('base64');
}

function aesGcmEncrypt(plaintext, keyBase64) {
    const key = Buffer.from(keyBase64, 'base64');
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    const enc = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    return {
        ciphertext: enc.toString('base64'),
        iv: iv.toString('base64'),
        tag: tag.toString('base64')
    };
}

function aesGcmEncryptFixedIv(plaintext, keyBase64, ivBase64) {
    const key = Buffer.from(keyBase64, 'base64');
    const iv = Buffer.from(ivBase64, 'base64');
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    const enc = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    return {
        ciphertext: enc.toString('base64'),
        iv: iv.toString('base64'),
        tag: tag.toString('base64')
    };
}

// 32-byte base64 key (matches Encryption constructor expectation).
const keyBase64 = crypto.randomBytes(32).toString('base64');
const fixedIvBase64 = Buffer.from('0123456789ab', 'utf8').toString('base64'); // 12 bytes

const vectors = {
    pbkdf2: [
        {
            plaintext: 'nango_connect_session_abcdef',
            encryption_key: 'test-encryption-key',
            hash: pbkdf2Hash('nango_connect_session_abcdef', 'test-encryption-key')
        },
        {
            plaintext: '11111111-1111-4111-8111-111111111111',
            encryption_key: keyBase64,
            hash: pbkdf2Hash('11111111-1111-4111-8111-111111111111', keyBase64)
        }
    ],
    aes_gcm: [
        {
            plaintext: 'super-secret-api-key-value',
            key_base64: keyBase64,
            ...aesGcmEncryptFixedIv('super-secret-api-key-value', keyBase64, fixedIvBase64)
        },
        {
            plaintext: '{"apiKey":"abc","token":"def"}',
            key_base64: keyBase64,
            ...aesGcmEncrypt('{"apiKey":"abc","token":"def"}', keyBase64)
        }
    ]
};

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, JSON.stringify(vectors, null, 2) + '\n');
console.log(`wrote ${outPath}`);
console.log(`pbkdf2[0].hash=${vectors.pbkdf2[0].hash}`);