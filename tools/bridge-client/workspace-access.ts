import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHmac, randomBytes } from 'node:crypto';

export const workspaceAuthHeader = 'X-Pikachu-Workspace-Auth';
let cachedKey: Buffer | undefined;

function loadWorkspaceKey(): Buffer {
  if (cachedKey) return cachedKey;
  const parent = process.env.LOCALAPPDATA;
  if (!parent) throw new Error('缺少本机用户数据目录');
  const directory = join(parent, 'PikachuSmsBridge');
  const file = join(directory, 'workspace-access.key');
  mkdirSync(directory, { recursive: true });
  try {
    writeFileSync(file, randomBytes(32).toString('hex'), { encoding: 'ascii', flag: 'wx', mode: 0o600 });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
  }
  const raw = readFileSync(file, 'ascii').trim();
  if (!/^[0-9a-f]{64}$/.test(raw)) throw new Error('本机访问凭据无效，请重新启动客户端');
  cachedKey = Buffer.from(raw, 'hex');
  return cachedKey;
}

export function isWorkspaceTarget(value: string): boolean {
  try {
    const url = new URL(value);
    const port = Number(url.port);
    return url.protocol === 'http:' && url.hostname === '127.0.0.1' && !url.username && !url.password &&
      (port === 8070 || (port >= 8080 && port <= 65535));
  } catch { return false; }
}

export function signWorkspaceRequest(method: string, value: string, key: Buffer,
  timestamp = String(Math.floor(Date.now() / 1000)), nonce = randomBytes(16).toString('hex')): string {
  if (!isWorkspaceTarget(value)) throw new Error('无效的工作台地址');
  const url = new URL(value);
  const payload = `v1\n${method.toUpperCase()}\n${url.port}\n${url.pathname}${url.search}\n${timestamp}\n${nonce}`;
  const signature = createHmac('sha256', key).update(payload, 'utf8').digest('hex');
  return `v1:${timestamp}:${nonce}:${signature}`;
}

export function workspaceAccessHeaders(platform: string, method: string, url: string,
  headers: Record<string, string>, getKey: () => Buffer = loadWorkspaceKey): Record<string, string> {
  const result = Object.fromEntries(Object.entries(headers).filter(([name]) => name.toLowerCase() !== workspaceAuthHeader.toLowerCase()));
  if (platform === 'apple' && isWorkspaceTarget(url)) result[workspaceAuthHeader] = signWorkspaceRequest(method, url, getKey());
  return result;
}
