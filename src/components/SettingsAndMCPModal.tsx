import React, { useState } from 'react';
import { Cpu, GitBranch, Globe, Layers, Shield, X } from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  config: Record<string, any> | null;
  onUpdateConfig: (patch: Record<string, any>) => Promise<void>;
}

export const SettingsAndMCPModal: React.FC<Props> = ({
  isOpen,
  onClose,
  config,
  onUpdateConfig,
}) => {
  const [tab, setTab] = useState<'mcp' | 'llm' | 'security'>('mcp');
  const [draft, setDraft] = useState<Record<string, any>>(config || {});
  const [saving, setSaving] = useState(false);

  React.useEffect(() => {
    if (config) {
      setDraft(JSON.parse(JSON.stringify(config)));
    }
  }, [config]);

  if (!isOpen || !config) return null;

  const updateNested = (section: string, field: string, value: any) => {
    setDraft((prev) => ({
      ...prev,
      [section]: {
        ...(prev[section] || {}),
        [field]: value,
      },
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onUpdateConfig(draft);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-white/[0.08] bg-[#111114] shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-modal-pop">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-6">
            <h2 className="text-sm font-semibold text-white">Preferencias</h2>
            <div className="flex items-center gap-1 bg-white/[0.04] p-1 rounded-lg">
              {[
                { id: 'mcp', label: 'Conectores MCP', icon: Layers },
                { id: 'llm', label: 'Motores LLM', icon: Cpu },
                { id: 'security', label: 'Seguridad HITL', icon: Shield },
              ].map((t) => {
                const Icon = t.icon;
                return (
                  <button
                    key={t.id}
                    onClick={() => setTab(t.id as any)}
                    className={`px-3 py-1 rounded-md text-xs font-medium flex items-center gap-1.5 transition ${
                      tab === t.id
                        ? 'bg-white/[0.1] text-white'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{t.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/[0.05] text-zinc-400 hover:text-white transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-xs">
          {tab === 'mcp' && (
            <>
              {/* Atlassian */}
              <div className="rounded-xl border border-white/[0.06] bg-[#0B0B0D] p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Globe className="w-4 h-4 text-blue-400" />
                    <span className="font-semibold text-white">Atlassian Cloud (Jira & Confluence)</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={Boolean(draft.atlassian?.enabled)}
                    onChange={(e) => updateNested('atlassian', 'enabled', e.target.checked)}
                    className="accent-[#EC0000]"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Cloud URL</label>
                    <input
                      type="text"
                      value={draft.atlassian?.cloud_url || ''}
                      onChange={(e) => updateNested('atlassian', 'cloud_url', e.target.value)}
                      placeholder="https://santander.atlassian.net"
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono focus:outline-none focus:border-zinc-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Email corporativo</label>
                    <input
                      type="email"
                      value={draft.atlassian?.user_email || ''}
                      onChange={(e) => updateNested('atlassian', 'user_email', e.target.value)}
                      placeholder="nombre@santander.com"
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white focus:outline-none focus:border-zinc-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Proyecto Jira</label>
                    <input
                      type="text"
                      value={draft.atlassian?.default_jira_project || ''}
                      onChange={(e) => updateNested('atlassian', 'default_jira_project', e.target.value)}
                      placeholder="SAN"
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono focus:outline-none focus:border-zinc-500"
                    />
                  </div>
                </div>
              </div>

              {/* GitHub */}
              <div className="rounded-xl border border-white/[0.06] bg-[#0B0B0D] p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-zinc-300" />
                    <span className="font-semibold text-white">GitHub.com MCP</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={Boolean(draft.github?.enabled)}
                    onChange={(e) => updateNested('github', 'enabled', e.target.checked)}
                    className="accent-[#EC0000]"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">API Base</label>
                    <input
                      type="text"
                      value={draft.github?.api_base_url || 'https://api.github.com'}
                      onChange={(e) => updateNested('github', 'api_base_url', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Owner / Org</label>
                    <input
                      type="text"
                      value={draft.github?.default_owner || ''}
                      onChange={(e) => updateNested('github', 'default_owner', e.target.value)}
                      placeholder="santander"
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Repositorio</label>
                    <input
                      type="text"
                      value={draft.github?.default_repo || ''}
                      onChange={(e) => updateNested('github', 'default_repo', e.target.value)}
                      placeholder="micelio-desktop"
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono focus:outline-none"
                    />
                  </div>
                </div>
              </div>
            </>
          )}

          {tab === 'llm' && (
            <div className="space-y-4">
              {/* Phoenix */}
              <div className="rounded-xl border border-white/[0.06] bg-[#0B0B0D] p-4 space-y-3">
                <div className="font-semibold text-white flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#EC0000]"></span>
                  <span>Santander `phoenix` (Librería Python interna)</span>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Módulo</label>
                    <input
                      type="text"
                      value={draft.phoenix?.module_name || 'phoenix'}
                      onChange={(e) => updateNested('phoenix', 'module_name', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Clase / Función</label>
                    <input
                      type="text"
                      value={draft.phoenix?.client_class_or_fn || 'PhoenixClient'}
                      onChange={(e) => updateNested('phoenix', 'client_class_or_fn', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Model ID</label>
                    <input
                      type="text"
                      value={draft.phoenix?.model_id || ''}
                      onChange={(e) => updateNested('phoenix', 'model_id', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* AWS Boto3 */}
              <div className="rounded-xl border border-white/[0.06] bg-[#0B0B0D] p-4 space-y-3">
                <div className="font-semibold text-white">AWS Boto3 (Lambda / Bedrock)</div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Modo</label>
                    <select
                      value={draft.boto3?.invocation_mode || 'bedrock'}
                      onChange={(e) => updateNested('boto3', 'invocation_mode', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white"
                    >
                      <option value="bedrock">Bedrock Runtime</option>
                      <option value="lambda">AWS Lambda Proxy</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Región AWS</label>
                    <input
                      type="text"
                      value={draft.boto3?.aws_region || 'eu-west-1'}
                      onChange={(e) => updateNested('boto3', 'aws_region', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Función Lambda</label>
                    <input
                      type="text"
                      value={draft.boto3?.lambda_function_name || ''}
                      onChange={(e) => updateNested('boto3', 'lambda_function_name', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Anthropic */}
              <div className="rounded-xl border border-white/[0.06] bg-[#0B0B0D] p-4 space-y-3">
                <div className="font-semibold text-white">Anthropic Direct (Local)</div>
                <div className="grid grid-cols-2 gap-3 items-center">
                  <div>
                    <label className="block text-[11px] text-zinc-500 mb-1">Modelo</label>
                    <select
                      value={draft.anthropic?.model_id || 'claude-sonnet-4-5'}
                      onChange={(e) => updateNested('anthropic', 'model_id', e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-[#141418] border border-white/[0.07] text-white font-mono"
                    >
                      <option value="claude-sonnet-4-5">claude-sonnet-4-5</option>
                      <option value="claude-3-7-sonnet-latest">claude-3-7-sonnet-latest</option>
                      <option value="claude-3-5-sonnet-latest">claude-3-5-sonnet-latest</option>
                      <option value="claude-3-5-haiku-latest">claude-3-5-haiku-latest</option>
                    </select>
                  </div>
                  <label className="flex items-center gap-2 pt-4 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={Boolean(draft.anthropic?.enable_thinking)}
                      onChange={(e) => updateNested('anthropic', 'enable_thinking', e.target.checked)}
                      className="accent-[#EC0000]"
                    />
                    <span className="text-zinc-300">Activar Razonamiento Extendido (`thinking`)</span>
                  </label>
                </div>
              </div>
            </div>
          )}

          {tab === 'security' && (
            <div className="rounded-xl border border-white/[0.06] bg-[#0B0B0D] p-4 space-y-3">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(draft.security?.require_approval_for_destructive_commands)}
                  onChange={(e) =>
                    updateNested('security', 'require_approval_for_destructive_commands', e.target.checked)
                  }
                  className="accent-[#EC0000]"
                />
                <span className="text-zinc-200">
                  Pedir confirmación humana (HITL) antes de comandos destructivos (`rm -rf`, `git push --force`)
                </span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(draft.security?.require_approval_for_commands)}
                  onChange={(e) =>
                    updateNested('security', 'require_approval_for_commands', e.target.checked)
                  }
                  className="accent-[#EC0000]"
                />
                <span className="text-zinc-200">
                  Pedir confirmación humana para cualquier comando de terminal fuera de la lista blanca
                </span>
              </label>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-3.5 border-t border-white/[0.06]">
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg hover:bg-white/[0.05] text-zinc-400 text-xs transition"
          >
            Cancelar
          </button>
          <button
            disabled={saving}
            onClick={handleSave}
            className="px-4 py-1.5 rounded-lg bg-[#EC0000] hover:bg-[#D00000] text-white text-xs font-medium transition"
          >
            Guardar cambios
          </button>
        </div>
      </div>
    </div>
  );
};
