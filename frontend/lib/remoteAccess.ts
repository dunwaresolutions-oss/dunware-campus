import { api } from "./api";

export interface RemoteAccessStatus {
  enabled: boolean;
  mode: string;
  hosts: string[];
  client_ip_header: string;
  service: string;
  hotfixes: string[];
  build: { version: string; frozen: boolean; python: string; git?: string; exe_built?: string };
  manage_hint: string;
}

export function remoteAccessStatus(): Promise<RemoteAccessStatus> {
  return api<RemoteAccessStatus>("/remote-access/status/");
}
