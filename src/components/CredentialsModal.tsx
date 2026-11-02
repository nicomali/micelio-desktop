import React, { useState } from 'react';
import {
  Check,
  KeyRound,
  Link2,
  Lock,
  RefreshCw,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import { CredentialStatus, WindowsTargetItem } from '../types';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  credentials: CredentialStatus[];
  windowsTargets: WindowsTargetItem[];
  onSaveSecret: (key: string, secret: string, customTarget?: string) => Promise<void>;
  onLinkTarget: (key: string, targetName: string) => Promise<void>;
  onDeleteSecret: (key: string) => Promise<void>;
  onRefresh: () => Promise<void>;
}

export const CredentialsModal: React.FC<Props> = ({
  isOpen,
  onClose,
  credentials,
  windowsTargets,
  onSaveSecret,
  onLinkTarget,
  onDeleteSecret,
  onRefresh,
}) => {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [secretInput, setSecretInput] = useState('');
  const [customTargetInput, setCustomTargetInput] = useState('');
  const [linkingKey, setLinkingKey] = useState<string | null>(null);
  const [selectedExistingTarget, setSelectedExistingTarget] = useState('');
  const [busy, setBusy] = useState(false);

  if (!isOpen) return null;

  const handleSave = async (key: string) => {
    if (!secretInput.trim()) return;
    setBusy(true);
    try {
      await onSaveSecret(key, secretInput.trim(), customTargetInput.trim() || undefined);
      setEditingKey(null);
      setSecretInput('');
      setCustomTargetInput('');
    } finally {
      setBusy(false);
    }
  };

  const handleLink = async (key: string) => {
    if (!selectedExistingTarget.trim()) return;
    setBusy(true);
    try {
      await onLinkTarget(key, selectedExistingTarget.trim());
      setLinkingKey(null);
      setSelectedExistingTarget('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-white/[0.08] bg-[#111114] shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-modal-pop">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#EC0000]/10 border border-[#EC0000]/25 flex items-center justify-center text-[#EC0000]">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">
                Windows Credential Manager
              </h2>
              <p className="text-xs text-zinc-400">
                Cifrado nativo DPAPI (`WinCred`). Cero secretos en texto plano en disco.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={onRefresh}
              className="px-2.5 py-1.5 rounded-lg hover:bg-white/[0.05] text-zinc-400 hover:text-zinc-200 text-xs flex items-center gap-1.5 transition"
              title="Sincronizar con Windows Credential Manager"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Sincronizar</span>
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-white/[0.05] text-zinc-400 hover:text-white transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* List */}
        <div className="p-5 overflow-y-auto divide-y divide-white/[0.05]">
          {credentials.map((cred) => (
            <div key={cred.key} className="py-3.5 first:pt-0 last:pb-0">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-zinc-100 truncate">
                      {cred.label}
                    </span>
                    {cred.is_configured ? (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <Check className="w-2.5 h-2.5" />
                        {cred.source === 'wincred' ? 'WinCred' : 'ENV'}
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-zinc-800 text-zinc-400">
                        Sin configurar
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-zinc-500 font-mono mt-0.5 flex items-center gap-3">
                    <span>{cred.target_name}</span>
                    {cred.masked_preview && (
                      <span className="text-zinc-400">{cred.masked_preview}</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    onClick={() => {
                      setEditingKey(editingKey === cred.key ? null : cred.key);
                      setLinkingKey(null);
                      setSecretInput('');
                      setCustomTargetInput(
                        cred.target_name.startsWith('ENV:') ? '' : cred.target_name
                      );
                    }}
                    className="px-2.5 py-1 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-zinc-200 text-xs font-medium transition"
                  >
                    {cred.is_configured ? 'Cambiar' : 'Configurar'}
                  </button>

                  <button
                    onClick={() => {
                      setLinkingKey(linkingKey === cred.key ? null : cred.key);
                      setEditingKey(null);
                      setSelectedExistingTarget(cred.target_name);
                    }}
                    className="p-1.5 rounded-lg hover:bg-white/[0.06] text-zinc-400 hover:text-zinc-200 transition"
                    title="Vincular credencial existente en Windows"
                  >
                    <Link2 className="w-3.5 h-3.5" />
                  </button>

                  {cred.is_configured && cred.source === 'wincred' && (
                    <button
                      onClick={() => onDeleteSecret(cred.key)}
                      className="p-1.5 rounded-lg hover:bg-red-500/10 text-zinc-500 hover:text-red-400 transition"
                      title="Eliminar de Windows Credential Manager"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              {editingKey === cred.key && (
                <div className="mt-3 p-3 rounded-xl bg-[#0B0B0D] border border-white/[0.06] flex items-center gap-2">
                  <Lock className="w-3.5 h-3.5 text-zinc-500 ml-1 shrink-0" />
                  <input
                    type="password"
                    autoFocus
                    value={secretInput}
                    onChange={(e) => setSecretInput(e.target.value)}
                    placeholder={`Pegar token o clave para ${cred.key}...`}
                    className="flex-1 bg-transparent text-xs text-white placeholder-zinc-600 focus:outline-none font-mono"
                  />
                  <button
                    disabled={busy}
                    onClick={() => handleSave(cred.key)}
                    className="px-3 py-1 rounded-lg bg-[#EC0000] hover:bg-[#D00000] text-white text-xs font-medium transition"
                  >
                    Guardar
                  </button>
                </div>
              )}

              {linkingKey === cred.key && (
                <div className="mt-3 p-3 rounded-xl bg-[#0B0B0D] border border-white/[0.06] space-y-2">
                  <div className="text-[11px] text-zinc-400">
                    Vincular con una entrada existente del Administrador de Credenciales de Windows:
                  </div>
                  <div className="flex items-center gap-2">
                    <select
                      value={selectedExistingTarget}
                      onChange={(e) => setSelectedExistingTarget(e.target.value)}
                      className="flex-1 px-2.5 py-1.5 rounded-lg bg-[#141418] border border-white/[0.08] text-xs text-zinc-200 focus:outline-none"
                    >
                      <option value="">Seleccionar de Windows ({windowsTargets.length})...</option>
                      {windowsTargets.map((t) => (
                        <option key={t.target_name} value={t.target_name}>
                          {t.target_name}
                        </option>
                      ))}
                    </select>
                    <button
                      disabled={busy}
                      onClick={() => handleLink(cred.key)}
                      className="px-3 py-1.5 rounded-lg bg-[#EC0000] hover:bg-[#D00000] text-white text-xs font-medium transition"
                    >
                      Vincular
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
