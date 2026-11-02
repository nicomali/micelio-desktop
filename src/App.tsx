import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  Bot,
  Brain,
  Check,
  ChevronRight,
  Clock,
  FileCode2,
  FileText,
  FolderOpen,
  GitBranch,
  HelpCircle,
  KeyRound,
  Layers,
  Moon,
  PanelLeft,
  PanelRight,
  Pencil,
  Plus,
  Settings,
  ShieldAlert,
  Sparkles,
  Sun,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import {
  ArtifactItem,
  ChatMessage,
  CredentialStatus,
  HITLApprovalRequest,
  QuestionItem,
  ToolCallItem,
  WindowsTargetItem,
} from './types';
import { RichMarkdown } from './components/RichMarkdown';
import { CredentialsModal } from './components/CredentialsModal';
import { SettingsAndMCPModal } from './components/SettingsAndMCPModal';
import { WorkspaceModal } from './components/WorkspaceModal';

const ENGINE_HTTP = 'http://127.0.0.1:8765';
const ENGINE_WS = 'ws://127.0.0.1:8765/ws';

const SLASH_COMMANDS = [
  { cmd: '/plan', label: 'Plan Operativo', desc: 'Armar plan paso a paso antes de procesar' },
  { cmd: '/grill-me', label: 'Validar Reglas', desc: 'Clarificar criterios de negocio antes de actuar' },
  { cmd: '/teamwork', label: 'Paralelo', desc: 'Cruzar varias fuentes en simultáneo' },
  { cmd: '/boost', label: 'Auditoría', desc: 'Doble control de totales y cuadratura' },
  { cmd: '/schedule', label: 'Programar', desc: 'Dejar rutina o monitoreo programado' },
  { cmd: '/learn', label: 'Guardar SOP', desc: 'Guardar este flujo como Playbook repetible' },
];

const PROVIDERS = [
  { id: 'phoenix', label: 'Phoenix', sub: 'Santander' },
  { id: 'boto3', label: 'AWS Bedrock', sub: 'Boto3 / Lambda' },
  { id: 'anthropic', label: 'Claude Direct', sub: 'Local Key' },
];

export default function App() {
  const [conversations, setConversations] = useState<
    Array<{ id: string; title: string; updated_at: string }>
  >([]);
  const [activeConvId, setActiveConvId] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactItem | null>(null);

  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightTab, setRightTab] = useState<'file' | 'artifact' | 'activity'>('artifact');
  const [previewFile, setPreviewFile] = useState<{
    name: string;
    path: string;
    content: string;
  } | null>(null);

  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [activeProvider, setActiveProvider] = useState<string>('anthropic');
  const [workspaceFiles, setWorkspaceFiles] = useState<Array<{ name: string; rel_path: string }>>(
    []
  );
  const [workspacePath, setWorkspacePath] = useState<string>('');

  const [credentials, setCredentials] = useState<CredentialStatus[]>([]);
  const [windowsTargets, setWindowsTargets] = useState<WindowsTargetItem[]>([]);
  const [runtimeStatus, setRuntimeStatus] = useState<{
    tasks: any[];
    subagents: any[];
    schedules: any[];
    skills: any[];
    playbooks?: any[];
    mcp_tools: any[];
  }>({ tasks: [], subagents: [], schedules: [], skills: [], playbooks: [], mcp_tools: [] });

  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingThinking, setStreamingThinking] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [streamingToolCalls, setStreamingToolCalls] = useState<ToolCallItem[]>([]);

  const [pendingQuestions, setPendingQuestions] = useState<QuestionItem[] | null>(null);
  const [questionAnswers, setQuestionAnswers] = useState<Record<string, string>>({});
  const [pendingApproval, setPendingApproval] = useState<HITLApprovalRequest | null>(null);

  const [credModalOpen, setCredModalOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [workspaceModalOpen, setWorkspaceModalOpen] = useState(false);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [editingConvId, setEditingConvId] = useState<string | null>(null);
  const [editingConvTitle, setEditingConvTitle] = useState<string>('');

  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void bootstrap();
    connectWebSocket();
    const interval = setInterval(() => {
      void fetchRuntimeStatus();
    }, 5000);
    return () => {
      clearInterval(interval);
      wsRef.current?.close();
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [
    messages,
    streamingText,
    streamingThinking,
    streamingToolCalls,
    pendingQuestions,
    pendingApproval,
  ]);

  const bootstrap = async () => {
    try {
      const [cfgRes, convRes, credRes, treeRes, rtRes] = await Promise.all([
        fetch(`${ENGINE_HTTP}/api/config`).then((r) => r.json()),
        fetch(`${ENGINE_HTTP}/api/conversations`).then((r) => r.json()),
        fetch(`${ENGINE_HTTP}/api/credentials`).then((r) => r.json()),
        fetch(`${ENGINE_HTTP}/api/workspace/tree`).then((r) => r.json()),
        fetch(`${ENGINE_HTTP}/api/runtime-status`).then((r) => r.json()),
      ]);

      setConfig(cfgRes);
      const initialTheme = cfgRes.theme === 'light' ? 'light' : 'dark';
      setTheme(initialTheme);
      document.documentElement.classList.toggle('light', initialTheme === 'light');
      document.documentElement.classList.toggle('dark', initialTheme === 'dark');
      setActiveProvider(cfgRes.active_provider || 'anthropic');
      setCredentials(credRes.credentials || []);
      setWindowsTargets(credRes.windows_targets || []);
      setWorkspacePath(treeRes.workspace || '');
      setWorkspaceFiles(treeRes.files || []);
      setRuntimeStatus(rtRes);

      const convList = convRes.conversations || [];
      setConversations(convList);
      if (convList.length > 0) {
        await selectConversation(convList[0].id);
      } else {
        await createNewConversation();
      }
    } catch (err) {
      console.error('Engine bootstrap error:', err);
    }
  };

  const fetchRuntimeStatus = async () => {
    try {
      const [rt, treeRes] = await Promise.all([
        fetch(`${ENGINE_HTTP}/api/runtime-status`).then((r) => r.json()),
        fetch(`${ENGINE_HTTP}/api/workspace/tree`).then((r) => r.json()),
      ]);
      setRuntimeStatus(rt);
      if (treeRes.workspace) {
        setWorkspacePath(treeRes.workspace);
        setWorkspaceFiles(treeRes.files || []);
      }
    } catch (_) {}
  };

  const BINARY_EXTENSIONS = new Set([
    'xlsx',
    'xls',
    'pptx',
    'ppt',
    'docx',
    'doc',
    'pdf',
    'png',
    'jpg',
    'jpeg',
    'zip',
  ]);

  const handleOpenFilePreview = async (relOrAbsPath: string) => {
    const cleanPath = relOrAbsPath.trim().replace(/^@/, '');
    const ext = cleanPath.split('.').pop()?.toLowerCase() || '';
    // If it's an Office/PDF/binary deliverable, open it directly in Excel/PowerPoint/Windows
    if (BINARY_EXTENSIONS.has(ext)) {
      await fetch(`${ENGINE_HTTP}/api/workspace/open-external`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: cleanPath }),
      });
      return;
    }

    try {
      const res = await fetch(
        `${ENGINE_HTTP}/api/workspace/file?path=${encodeURIComponent(cleanPath)}`
      ).then((r) => r.json());
      if (!res.error) {
        setPreviewFile({
          name: res.name,
          path: res.path,
          content: res.content || '',
        });
        setRightTab('file');
        setRightDrawerOpen(true);
      }
    } catch (_) {}
  };

  const fetchCredentials = async () => {
    const credRes = await fetch(`${ENGINE_HTTP}/api/credentials`).then((r) => r.json());
    setCredentials(credRes.credentials || []);
    setWindowsTargets(credRes.windows_targets || []);
  };

  const connectWebSocket = () => {
    const ws = new WebSocket(ENGINE_WS);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleWsEvent(data);
    };

    ws.onclose = () => {
      setTimeout(connectWebSocket, 2000);
    };
  };

  const handleWsEvent = (ev: Record<string, any>) => {
    switch (ev.type) {
      case 'turn_start':
        setIsStreaming(true);
        setStreamingThinking('');
        setStreamingText('');
        setStreamingToolCalls([]);
        break;
      case 'thinking_delta':
        setStreamingThinking((prev) => prev + (ev.delta || ''));
        break;
      case 'text_delta':
        setStreamingText((prev) => prev + (ev.delta || ''));
        break;
      case 'tool_call_start':
        if (ev.tool_call) {
          setStreamingToolCalls((prev) => [...prev, ev.tool_call]);
        }
        break;
      case 'tool_call_result':
        setStreamingToolCalls((prev) =>
          prev.map((tc) =>
            tc.id === ev.tool_call_id
              ? { ...tc, output: ev.output, is_error: ev.is_error }
              : tc
          )
        );
        break;
      case 'file_deleted':
        void fetchRuntimeStatus();
        break;
      case 'file_written':
      case 'file_edited':
        void fetchRuntimeStatus();
        break;
      case 'artifact_updated':
        if (ev.artifact) {
          const updatedArt: ArtifactItem = {
            ...ev.artifact,
            content: ev.content || '',
          };
          setArtifacts((prev) => {
            const exists = prev.some((a) => a.name === updatedArt.name);
            return exists
              ? prev.map((a) => (a.name === updatedArt.name ? updatedArt : a))
              : [updatedArt, ...prev];
          });
          setSelectedArtifact(updatedArt);
          setRightTab('artifact');
          setRightDrawerOpen(true);
        }
        break;
      case 'ask_question':
        setPendingQuestions(ev.questions || []);
        setQuestionAnswers({});
        break;
      case 'hitl_approval_request':
        setPendingApproval(ev as HITLApprovalRequest);
        break;
      case 'turn_complete':
        setIsStreaming(false);
        if (ev.conversation_id) {
          void selectConversation(ev.conversation_id);
        }
        void fetchRuntimeStatus();
        break;
      case 'error':
        setIsStreaming(false);
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `> [!WARNING]\n> ${ev.message}` },
        ]);
        break;
      default:
        break;
    }
  };

  const fetchConversationsList = async (projPath?: string) => {
    const p = projPath ?? workspacePath;
    const q = p ? `?project_path=${encodeURIComponent(p)}` : '';
    const convRes = await fetch(`${ENGINE_HTTP}/api/conversations${q}`).then((r) => r.json());
    const list = convRes.conversations || [];
    setConversations(list);
    return list;
  };

  const createNewConversation = async (projOverride?: string) => {
    const res = await fetch(`${ENGINE_HTTP}/api/conversations/new`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: projOverride || workspacePath }),
    }).then((r) => r.json());
    const cid = res.conversation_id;
    setActiveConvId(cid);
    setMessages([]);
    setArtifacts([]);
    setSelectedArtifact(null);
    await fetchConversationsList(projOverride || workspacePath);
  };

  const selectConversation = async (cid: string) => {
    setActiveConvId(cid);
    const detail = await fetch(`${ENGINE_HTTP}/api/conversations/${cid}`).then((r) => r.json());
    setMessages(detail.messages || []);
    const arts: ArtifactItem[] = detail.artifacts || [];
    setArtifacts(arts);
    if (arts.length > 0) {
      setSelectedArtifact(arts[0]);
    } else {
      setSelectedArtifact(null);
    }
    await fetchConversationsList();
  };

  const handleRenameConversation = async (cid: string, newTitle: string) => {
    if (!newTitle.trim()) {
      setEditingConvId(null);
      return;
    }
    await fetch(`${ENGINE_HTTP}/api/conversations/${cid}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle.trim() }),
    });
    setEditingConvId(null);
    await fetchConversationsList();
  };

  const handleDeleteConversation = async (cid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await fetch(`${ENGINE_HTTP}/api/conversations/${cid}`, { method: 'DELETE' });
    const remaining = await fetchConversationsList();
    if (activeConvId === cid) {
      if (remaining.length > 0) {
        await selectConversation(remaining[0].id);
      } else {
        await createNewConversation();
      }
    }
  };

  const handleToggleTheme = async () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    document.documentElement.classList.toggle('light', next === 'light');
    document.documentElement.classList.toggle('dark', next === 'dark');
    const updated = await fetch(`${ENGINE_HTTP}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: next }),
    }).then((r) => r.json());
    setConfig(updated);
  };

  const handleSendMessage = () => {
    const text = input.trim();
    if (!text || !wsRef.current) return;

    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setIsStreaming(true);

    wsRef.current.send(
      JSON.stringify({
        action: 'chat',
        conversation_id: activeConvId,
        message: text,
        provider_override: activeProvider,
      })
    );
  };

  const handleSwitchProvider = async (providerId: string) => {
    setActiveProvider(providerId);
    const updated = await fetch(`${ENGINE_HTTP}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active_provider: providerId }),
    }).then((r) => r.json());
    setConfig(updated);
  };

  const handleSelectWorkspace = async (newPath: string, projectName?: string) => {
    if (!newPath.trim()) return;
    const clean = newPath.trim().replace(/\\/g, '/');
    const projTitle = projectName || clean.split('/').filter(Boolean).pop() || 'Proyecto';

    const existingProjects: Array<{ name: string; path: string }> = config?.saved_projects || [];
    const filtered = existingProjects.filter(
      (p) => p.path.replace(/\\/g, '/').toLowerCase() !== clean.toLowerCase()
    );
    const updatedProjects = [{ name: projTitle, path: clean }, ...filtered];

    const updated = await fetch(`${ENGINE_HTTP}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        active_workspace: clean,
        saved_projects: updatedProjects,
      }),
    }).then((r) => r.json());
    setConfig(updated);
    const treeRes = await fetch(`${ENGINE_HTTP}/api/workspace/tree`).then((r) => r.json());
    const resolvedWs = treeRes.workspace || clean;
    setWorkspacePath(resolvedWs);
    setWorkspaceFiles(treeRes.files || []);
    const projConvs = await fetchConversationsList(resolvedWs);
    if (projConvs.length > 0) {
      await selectConversation(projConvs[0].id);
    } else {
      await createNewConversation(resolvedWs);
    }
    await fetchRuntimeStatus();
  };

  const handleRemoveSavedProject = async (pathToRemove: string) => {
    const existingProjects: Array<{ name: string; path: string }> = config?.saved_projects || [];
    const updatedProjects = existingProjects.filter(
      (p) => p.path.replace(/\\/g, '/').toLowerCase() !== pathToRemove.replace(/\\/g, '/').toLowerCase()
    );
    const updated = await fetch(`${ENGINE_HTTP}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ saved_projects: updatedProjects }),
    }).then((r) => r.json());
    setConfig(updated);
  };

  const handleSubmitQuestions = () => {
    if (!wsRef.current || !pendingQuestions) return;
    wsRef.current.send(
      JSON.stringify({
        action: 'answer_question',
        conversation_id: activeConvId,
        answers: questionAnswers,
      })
    );
    setPendingQuestions(null);
  };

  const handleResolveApproval = (approved: boolean) => {
    if (!wsRef.current || !pendingApproval) return;
    wsRef.current.send(
      JSON.stringify({
        action: 'resolve_approval',
        approval_id: pendingApproval.approval_id,
        approved,
      })
    );
    setPendingApproval(null);
  };

  const handleArtifactFeedback = async (approved: boolean) => {
    if (!selectedArtifact) return;
    await fetch(`${ENGINE_HTTP}/api/artifacts/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: activeConvId,
        artifact_name: selectedArtifact.name,
        approved,
        comments: feedbackComment,
      }),
    });
    setFeedbackComment('');
  };

  const configuredCredCount = credentials.filter((c) => c.is_configured).length;
  const workspaceFolderName = workspacePath.split('/').filter(Boolean).pop() || 'workspace';
  const activeBgCount =
    runtimeStatus.subagents.filter((s) => s.status === 'running').length +
    runtimeStatus.tasks.filter((t) => t.status === 'running').length;

  return (
    <div className="h-screen w-screen flex flex-col bg-[#09090B] text-zinc-100 overflow-hidden">
      {/* Ultra-subtle Top Accent Line (Santander Touch) */}
      <div className="h-[2px] w-full bg-gradient-to-r from-[#EC0000] via-[#EC0000]/40 to-transparent shrink-0" />

      {/* Minimal Header Bar */}
      <header className="h-11 px-3 border-b border-white/[0.06] bg-[#09090B] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setLeftSidebarOpen((v) => !v)}
            className="p-1.5 rounded-lg hover:bg-white/[0.05] text-zinc-400 hover:text-zinc-200 transition"
            title="Mostrar/ocultar panel lateral"
          >
            <PanelLeft className="w-4 h-4" />
          </button>

          <div className="h-3.5 w-[1px] bg-white/[0.08] mx-0.5" />

          <div className="flex items-center gap-2">
            <img src="./icon.svg" alt="Micelio" className="w-4 h-4 rounded-sm" />
            <span className="font-semibold text-xs tracking-tight text-white">Micelio</span>
            <span className="text-[11px] text-zinc-500 font-medium">Santander</span>
          </div>

          <span className="text-zinc-700 text-xs">/</span>

          <button
            onClick={() => setWorkspaceModalOpen(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.09] active:scale-[0.98] border border-white/[0.07] hover:border-white/[0.15] text-[11px] text-zinc-200 font-medium transition-all group"
            title={`Proyecto activo: ${workspacePath} (Clic para cambiar de Proyecto)`}
          >
            <FolderOpen className="w-3.5 h-3.5 text-[#EC0000] group-hover:scale-110 transition-transform" />
            <span className="text-zinc-500">Proyecto:</span>
            <span className="font-semibold text-white">{workspaceFolderName}</span>
            <span className="text-[10px] text-zinc-400 group-hover:text-[#EC0000] ml-1">
              Cambiar
            </span>
          </button>
        </div>

        {/* Right Controls: Theme Toggle, MCP Status, WinCred Vault, Drawer Toggle */}
        <div className="flex items-center gap-1.5">
          {/* Light / Dark Mode Toggle */}
          <button
            onClick={handleToggleTheme}
            className="px-2.5 py-1 rounded-lg hover:bg-white/[0.05] text-[11px] text-zinc-400 hover:text-zinc-200 flex items-center gap-1.5 transition"
            title={theme === 'dark' ? 'Cambiar a Modo Claro Santander' : 'Cambiar a Modo Oscuro'}
          >
            {theme === 'dark' ? (
              <>
                <Sun className="w-3.5 h-3.5 text-amber-400" />
                <span>Claro</span>
              </>
            ) : (
              <>
                <Moon className="w-3.5 h-3.5 text-zinc-600" />
                <span>Oscuro</span>
              </>
            )}
          </button>
          {/* MCP Status Pill */}
          <button
            onClick={() => setSettingsModalOpen(true)}
            className="px-2.5 py-1 rounded-lg hover:bg-white/[0.05] text-[11px] text-zinc-400 hover:text-zinc-200 flex items-center gap-2 transition"
            title="Configurar Conectores MCP (Jira, Confluence, GitHub) y Motores LLM"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>MCPs ({runtimeStatus.mcp_tools.length})</span>
          </button>

          {/* WinCred Pill */}
          <button
            onClick={() => setCredModalOpen(true)}
            className="px-2.5 py-1 rounded-lg hover:bg-white/[0.05] text-[11px] text-zinc-400 hover:text-zinc-200 flex items-center gap-1.5 transition"
            title="Administrador de Credenciales de Windows (WinCred)"
          >
            <KeyRound className="w-3.5 h-3.5 text-zinc-400" />
            <span>Credenciales</span>
            <span className="text-[10px] font-mono text-zinc-500">
              {configuredCredCount}/{credentials.length}
            </span>
          </button>

          <button
            onClick={() => setSettingsModalOpen(true)}
            className="p-1.5 rounded-lg hover:bg-white/[0.05] text-zinc-400 hover:text-zinc-200 transition"
            title="Preferencias"
          >
            <Settings className="w-4 h-4" />
          </button>

          <div className="h-3.5 w-[1px] bg-white/[0.08] mx-0.5" />

          {/* Toggle Right Drawer (Code Viewer / Artifacts / Activity) */}
          <button
            onClick={() => setRightDrawerOpen((v) => !v)}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium flex items-center gap-1.5 transition ${
              rightDrawerOpen || artifacts.length > 0 || previewFile
                ? 'bg-white/[0.07] text-zinc-100'
                : 'text-zinc-400 hover:bg-white/[0.05]'
            }`}
            title="Abrir/cerrar Visor de Código, Artifacts y Subagentes"
          >
            <PanelRight className="w-3.5 h-3.5" />
            <span>Visor</span>
            {artifacts.length > 0 && (
              <span className="px-1.5 rounded-full bg-[#EC0000] text-white text-[10px]">
                {artifacts.length}
              </span>
            )}
            {activeBgCount > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            )}
          </button>
        </div>
      </header>

      {/* Main Body */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Collapsible Minimal Left Sidebar */}
        {leftSidebarOpen && (
          <aside className="w-60 border-r border-white/[0.06] bg-[#0C0C0E] flex flex-col shrink-0">
            <div className="p-2.5">
              <button
                onClick={() => createNewConversation()}
                className="w-full py-1.5 px-3 rounded-lg bg-white/[0.05] hover:bg-white/[0.09] border border-white/[0.06] text-zinc-200 font-medium text-xs flex items-center justify-between transition group"
              >
                <span className="flex items-center gap-2">
                  <Plus className="w-3.5 h-3.5 text-[#EC0000]" />
                  <span>Nueva sesión</span>
                </span>
                <kbd className="text-[10px] text-zinc-500 font-mono">⌘N</kbd>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-2 py-1 space-y-5">
              {/* Project Sessions with Rename & Delete */}
              <div>
                <div className="px-2 mb-1.5 text-[10px] font-medium uppercase tracking-wider text-zinc-500">
                  Sesiones del Proyecto ({conversations.length})
                </div>
                <div className="space-y-0.5">
                  {conversations.map((c) => {
                    const active = activeConvId === c.id;
                    const isEditing = editingConvId === c.id;

                    if (isEditing) {
                      return (
                        <div
                          key={c.id}
                          className="px-2 py-1 rounded-lg bg-white/[0.08] flex items-center gap-1"
                        >
                          <input
                            type="text"
                            autoFocus
                            value={editingConvTitle}
                            onChange={(e) => setEditingConvTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                void handleRenameConversation(c.id, editingConvTitle);
                              } else if (e.key === 'Escape') {
                                setEditingConvId(null);
                              }
                            }}
                            onBlur={() => void handleRenameConversation(c.id, editingConvTitle)}
                            className="flex-1 bg-transparent text-xs text-white focus:outline-none"
                          />
                        </div>
                      );
                    }

                    return (
                      <div
                        key={c.id}
                        onClick={() => selectConversation(c.id)}
                        className={`group w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition flex items-center justify-between cursor-pointer ${
                          active
                            ? 'bg-white/[0.07] text-white font-medium'
                            : 'text-zinc-400 hover:bg-white/[0.03] hover:text-zinc-200'
                        }`}
                      >
                        <div className="flex items-center gap-2 truncate pr-1">
                          <span
                            className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                              active ? 'bg-[#EC0000]' : 'bg-transparent'
                            }`}
                          />
                          <span className="truncate">{c.title || 'Nueva sesión'}</span>
                        </div>

                        <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 shrink-0 transition">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingConvId(c.id);
                              setEditingConvTitle(c.title || '');
                            }}
                            className="p-1 rounded hover:bg-white/[0.1] text-zinc-400 hover:text-white"
                            title="Renombrar sesión"
                          >
                            <Pencil className="w-3 h-3" />
                          </button>
                          <button
                            onClick={(e) => handleDeleteConversation(c.id, e)}
                            className="p-1 rounded hover:bg-red-500/20 text-zinc-400 hover:text-red-400"
                            title="Eliminar sesión"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Workspace Playbooks / Workflows (if present in folder) */}
              {runtimeStatus.playbooks && runtimeStatus.playbooks.length > 0 && (
                <div>
                  <div className="px-2 mb-1.5 text-[10px] font-medium uppercase tracking-wider text-zinc-500">
                    Playbooks & Workflows ({runtimeStatus.playbooks.length})
                  </div>
                  <div className="space-y-1">
                    {runtimeStatus.playbooks.map((pb: any) => (
                      <div
                        key={pb.path}
                        className="group flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.05] text-xs transition"
                      >
                        <button
                          onClick={() => handleOpenFilePreview(pb.path)}
                          className="flex-1 text-left truncate text-zinc-200 font-medium"
                          title={`Ver ${pb.rel_path}`}
                        >
                          {pb.name}
                        </button>
                        <button
                          onClick={() =>
                            setInput(
                              `Ejecuta el playbook @${pb.rel_path} siguiendo sus instrucciones paso a paso.`
                            )
                          }
                          className="px-2 py-0.5 rounded bg-[#EC0000]/20 hover:bg-[#EC0000] text-[#FF5555] hover:text-white text-[10px] font-medium transition shrink-0"
                          title="Ejecutar este Playbook"
                        >
                          ▶ Run
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Workspace Files Explorer */}
              <div>
                <div className="px-2 mb-1.5 flex items-center justify-between">
                  <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">
                    Archivos en {workspaceFolderName} ({workspaceFiles.length})
                  </span>
                </div>
                {workspaceFiles.length === 0 ? (
                  <div className="px-2.5 py-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-[11px] text-zinc-500 leading-relaxed">
                    Esta carpeta aún no tiene archivos. Pídele al agente que cree uno o cambia de carpeta arriba.
                  </div>
                ) : (
                  <div className="space-y-0.5 max-h-56 overflow-y-auto">
                    {workspaceFiles.slice(0, 50).map((f) => (
                      <div
                        key={f.rel_path}
                        className="group flex items-center justify-between px-2 py-1 rounded-md hover:bg-white/[0.05] text-[11px] font-mono text-zinc-400 hover:text-zinc-200 transition"
                      >
                        <button
                          onClick={() => handleOpenFilePreview(f.rel_path)}
                          className="flex-1 text-left flex items-center gap-2 truncate"
                          title="Clic para ver el archivo en el visor derecho"
                        >
                          <FileCode2 className="w-3.5 h-3.5 shrink-0 text-zinc-500 group-hover:text-[#EC0000] transition" />
                          <span className="truncate">{f.rel_path}</span>
                        </button>
                        <button
                          onClick={() => setInput((prev) => `${prev} @${f.rel_path} `.trimStart())}
                          className="opacity-0 group-hover:opacity-100 px-1.5 py-0.2 rounded bg-white/[0.07] hover:bg-white/[0.15] text-[10px] text-zinc-300 transition shrink-0"
                          title="Mencionar @archivo en el chat"
                        >
                          @
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Footer: Installed Skills & Connectors */}
            <div className="p-3 border-t border-white/[0.05] text-[11px] text-zinc-500 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-zinc-500" />
                <span>Jira · Confluence · GitHub</span>
              </span>
              <span className="text-[10px] font-mono text-zinc-600">
                {runtimeStatus.skills.length} skills
              </span>
            </div>
          </aside>
        )}

        {/* Center Stage: Clean Antigravity/Cursor Conversation View */}
        <main className="flex-1 flex flex-col bg-[#09090B] overflow-hidden select-text">
          <div className="flex-1 overflow-y-auto px-6 pb-8 select-text">
            <div className="max-w-3xl mx-auto">
              {/* Empty State — Clean, Centered, Operations-Focused */}
              {messages.length === 0 && !isStreaming && (
                <div className="pt-14 pb-6 space-y-8 animate-fade-up">
                  <div className="space-y-2">
                    <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#EC0000]/10 border border-[#EC0000]/20 text-[#FF4D4D] text-[11px] font-medium">
                      <Sparkles className="w-3 h-3" />
                      <span>Entorno Productivo de Operaciones · Santander</span>
                    </div>
                    <h1 className="text-2xl font-semibold text-white tracking-tight">
                      ¿Qué proceso o gestión operativa realizamos hoy?
                    </h1>
                    <p className="text-sm text-zinc-400 max-w-xl">
                      Automatización de reportes Excel, presentaciones ejecutivas PowerPoint, ejecución de Playbooks operativos y seguimiento en <span className="text-zinc-200">Jira & Confluence</span>.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {[
                      {
                        label: 'Conciliación y Reportes en Excel',
                        desc: 'Cruza bases de datos, calcula KPIs/desvíos y exporta planillas formateadas',
                        prompt:
                          'Analiza los archivos de esta carpeta, genera un resumen de KPIs y exporta un reporte Excel ejecutivo',
                      },
                      {
                        label: 'Presentación Ejecutiva PowerPoint',
                        desc: 'Genera un deck 16:9 de comité con indicadores, tablas y gráficos',
                        prompt:
                          'Ármame una presentación PowerPoint ejecutiva con el resumen operativo, KPIs principales y próximos pasos',
                      },
                      {
                        label: 'Gestión de Tickets y SLAs en Jira & Confluence',
                        desc: 'Consulta estado de incidencias, bloqueos y procedimientos operativos',
                        prompt:
                          'Revisa los tickets activos en Jira, identifica desvíos o bloqueos y busca la normativa aplicable en Confluence',
                      },
                      {
                        label: 'Ejecutar Playbook / Flujo Operativo',
                        desc: 'Corre los procesos recurrentes o rutinas definidas en tu carpeta',
                        prompt:
                          '/plan Revisa los archivos e instrucciones de esta carpeta y propón el plan de ejecución operativa',
                      },
                    ].map((card, i) => (
                      <button
                        key={i}
                        onClick={() => setInput(card.prompt)}
                        className="text-left p-3.5 rounded-xl border border-white/[0.06] bg-white/[0.015] hover:bg-white/[0.04] hover:border-white/[0.12] transition group"
                      >
                        <div className="text-xs font-medium text-zinc-200 group-hover:text-white flex items-center justify-between">
                          <span>{card.label}</span>
                          <ChevronRight className="w-3.5 h-3.5 text-zinc-600 group-hover:text-[#EC0000] transition" />
                        </div>
                        <div className="text-[11px] text-zinc-500 mt-1">{card.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Conversation Turns (Each turn scopes its own sticky User Prompt) */}
              {(() => {
                const turnGroups: Array<{ userContent: string | null; steps: Message[] }> = [];
                for (const msg of messages) {
                  if (msg.role === 'tool') continue;
                  const raw = msg.content || '';
                  const isWakeup =
                    msg.role === 'user' &&
                    (raw.startsWith('[REACTIVE WAKEUP') || raw.startsWith('[SCHEDULED TRIGGER'));
                  if (msg.role === 'user' && !isWakeup) {
                    turnGroups.push({ userContent: raw, steps: [] });
                  } else {
                    if (turnGroups.length === 0) {
                      turnGroups.push({ userContent: null, steps: [msg] });
                    } else {
                      turnGroups[turnGroups.length - 1].steps.push(msg);
                    }
                  }
                }

                return turnGroups.map((turn, turnIdx) => {
                  const isLastTurn = turnIdx === turnGroups.length - 1;
                  return (
                    <section key={turnIdx} className="relative pb-6">
                      {turn.userContent !== null && (
                        <div className="sticky top-0 z-20 -mx-6 px-6 pt-3 pb-3 sticky-turn-wrapper">
                          <div className="w-full rounded-xl border px-4 py-2.5 text-[13.5px] text-zinc-100 user-prompt-card max-h-28 overflow-y-auto">
                            <RichMarkdown content={turn.userContent} />
                          </div>
                        </div>
                      )}

                      <div className="space-y-4 pt-2">
                        {turn.steps.map((msg, stepIdx) => {
                          const rawContent = msg.content || '';
                          if (msg.role === 'user') {
                            return (
                              <div key={stepIdx} className="flex justify-start">
                                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[11px] font-mono text-emerald-400">
                                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                  <span>Reactive Wakeup: tarea en segundo plano completada</span>
                                </div>
                              </div>
                            );
                          }

                          return (
                            <div key={stepIdx} className="space-y-2.5">
                              {/* Compact Thinking Pill */}
                              {msg.thinking && (
                                <details className="group">
                                  <summary className="list-none inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.05] text-[11px] text-zinc-400 cursor-pointer transition">
                                    <Brain className="w-3 h-3 text-zinc-400" />
                                    <span>Razonamiento del agente</span>
                                    <ChevronRight className="w-3 h-3 text-zinc-500 group-open:rotate-90 transition-transform" />
                                  </summary>
                                  <pre className="mt-2 p-3 rounded-xl bg-[#0D0D10] border border-white/[0.05] text-[11px] font-mono text-zinc-400 whitespace-pre-wrap leading-relaxed">
                                    {msg.thinking}
                                  </pre>
                                </details>
                              )}

                              {/* Compact Tool Call Pills (Antigravity Style) */}
                              {msg.tool_calls && msg.tool_calls.length > 0 && (
                                <div className="flex flex-wrap gap-1.5">
                                  {msg.tool_calls.map((tc) => {
                                    const filePath = tc.arguments?.Path
                                      ? String(tc.arguments.Path)
                                      : null;
                                    return (
                                      <div
                                        key={tc.id}
                                        onClick={() => {
                                          if (filePath) {
                                            void handleOpenFilePreview(filePath);
                                          }
                                        }}
                                        className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-[#111115] border border-white/[0.06] text-[11px] font-mono text-zinc-300 ${
                                          filePath
                                            ? 'cursor-pointer hover:border-[#EC0000]/50 hover:bg-white/[0.04] transition'
                                            : ''
                                        }`}
                                        title={
                                          filePath
                                            ? `Clic para abrir ${filePath} en el visor`
                                            : undefined
                                        }
                                      >
                                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                                        <span className="text-zinc-200 font-medium">{tc.name}</span>
                                        {filePath && (
                                          <span className="text-zinc-400 underline decoration-zinc-700 truncate max-w-[220px]">
                                            {filePath.split(/[\\/]/).pop()}
                                          </span>
                                        )}
                                        {tc.arguments?.CommandLine && (
                                          <span className="text-zinc-500 truncate max-w-[220px]">
                                            {tc.arguments.CommandLine}
                                          </span>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}

                              {/* Assistant Response */}
                              {msg.content && (
                                <div className="pl-0.5">
                                  <RichMarkdown content={msg.content} />
                                </div>
                              )}
                            </div>
                          );
                        })}

                        {/* Active Streaming Turn inside the latest TurnGroup */}
                        {isLastTurn && isStreaming && (
                          <div className="space-y-3 pt-1">
                            {streamingThinking && (
                              <div className="rounded-xl bg-[#0D0D10] border border-white/[0.06] p-3">
                                <div className="text-[11px] text-zinc-400 flex items-center gap-1.5 mb-1">
                                  <Brain className="w-3 h-3 text-[#EC0000] animate-pulse" />
                                  <span>Pensando...</span>
                                </div>
                                <pre className="text-[11px] font-mono text-zinc-400 whitespace-pre-wrap">
                                  {streamingThinking}
                                </pre>
                              </div>
                            )}

                            {streamingToolCalls.length > 0 && (
                              <div className="space-y-1.5">
                                {streamingToolCalls.map((tc) => (
                                  <details
                                    key={tc.id}
                                    className="rounded-xl bg-[#111115] border border-white/[0.06] px-3 py-2 text-xs font-mono"
                                  >
                                    <summary className="cursor-pointer flex items-center justify-between text-[11px]">
                                      <span className="flex items-center gap-2 text-zinc-200">
                                        <Terminal className="w-3.5 h-3.5 text-[#EC0000]" />
                                        <span>{tc.name}</span>
                                      </span>
                                      <span className="text-zinc-500">
                                        {tc.output ? 'Completado' : 'Ejecutando...'}
                                      </span>
                                    </summary>
                                    {tc.output && (
                                      <pre className="mt-2 pt-2 border-t border-white/[0.05] text-[11px] text-zinc-400 max-h-40 overflow-y-auto whitespace-pre-wrap">
                                        {tc.output}
                                      </pre>
                                    )}
                                  </details>
                                ))}
                              </div>
                            )}

                            {streamingText ? (
                              <RichMarkdown content={streamingText} />
                            ) : (
                              !streamingThinking &&
                              streamingToolCalls.length === 0 && (
                                <div className="flex items-center gap-2 text-xs text-zinc-500">
                                  <span className="w-1.5 h-1.5 rounded-full bg-[#EC0000] animate-ping" />
                                  <span>Generando respuesta...</span>
                                </div>
                              )
                            )}
                          </div>
                        )}
                      </div>
                    </section>
                  );
                });
              })()}

              {/* Interactive `ask_question` Card */}
              {pendingQuestions && (
                <div className="rounded-2xl border border-white/[0.1] bg-[#111115] p-5 space-y-4 shadow-xl">
                  <div className="flex items-center gap-2 text-zinc-200 font-medium text-xs">
                    <HelpCircle className="w-4 h-4 text-[#EC0000]" />
                    <span>Clarificación requerida</span>
                  </div>
                  {pendingQuestions.map((q, qIdx) => (
                    <div key={qIdx} className="space-y-2">
                      <div className="text-xs font-medium text-white">{q.question}</div>
                      <div className="space-y-1.5">
                        {q.options.map((opt, oIdx) => (
                          <label
                            key={oIdx}
                            className={`flex items-center gap-2.5 px-3 py-2 rounded-xl border cursor-pointer text-xs transition ${
                              questionAnswers[q.question] === opt
                                ? 'border-[#EC0000]/60 bg-[#EC0000]/[0.06] text-white'
                                : 'border-white/[0.06] bg-[#0B0B0D] text-zinc-300 hover:border-white/[0.15]'
                            }`}
                          >
                            <input
                              type="radio"
                              name={`q-${qIdx}`}
                              checked={questionAnswers[q.question] === opt}
                              onChange={() =>
                                setQuestionAnswers((prev) => ({ ...prev, [q.question]: opt }))
                              }
                              className="accent-[#EC0000]"
                            />
                            <span>{opt}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                  <button
                    onClick={handleSubmitQuestions}
                    className="px-4 py-1.5 rounded-lg bg-[#EC0000] hover:bg-[#D00000] text-white text-xs font-medium transition"
                  >
                    Continuar
                  </button>
                </div>
              )}

              {/* HITL Command Approval Banner */}
              {pendingApproval && (
                <div className="rounded-2xl border border-amber-500/30 bg-[#14120E] p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-amber-300 font-medium text-xs">
                      <ShieldAlert className="w-4 h-4" />
                      <span>Confirmar ejecución: {pendingApproval.summary}</span>
                    </div>
                  </div>
                  <pre className="p-2.5 rounded-xl bg-black/50 border border-white/[0.06] text-xs font-mono text-zinc-200 overflow-x-auto">
                    {pendingApproval.command_line}
                  </pre>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleResolveApproval(true)}
                      className="px-3.5 py-1.5 rounded-lg bg-white text-black hover:bg-zinc-200 text-xs font-medium transition"
                    >
                      Permitir comando
                    </button>
                    <button
                      onClick={() => handleResolveApproval(false)}
                      className="px-3.5 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-zinc-300 text-xs transition"
                    >
                      Rechazar
                    </button>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>
          </div>

          {/* Floating Unified Composer Box (Cursor / Antigravity / Linear Style) */}
          <div className="px-6 pb-5 pt-3 composer-Dock">
            <div className="max-w-3xl mx-auto">
              <div className="rounded-2xl border border-white/[0.09] bg-[#121216] focus-within:border-white/[0.18] shadow-2xl transition overflow-hidden">
                <textarea
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder="Pide un reporte Excel, una presentación PowerPoint, consulta Jira/Confluence o ejecuta un Playbook (@archivo)..."
                  className="w-full bg-transparent px-4 pt-3 pb-1 text-[13.5px] text-zinc-100 placeholder-zinc-500 focus:outline-none resize-none"
                />

                {/* Bottom Toolbar inside Composer */}
                <div className="px-3 py-2 flex items-center justify-between gap-2 border-t border-white/[0.04]">
                  {/* Left: Inline Model / Provider Selector + Slash Command Pills */}
                  <div className="flex items-center gap-1.5 overflow-x-auto">
                    {/* Provider Dropdown Pill */}
                    <div className="flex items-center bg-white/[0.04] rounded-lg p-0.5 border border-white/[0.05]">
                      {PROVIDERS.map((p) => {
                        const active = activeProvider === p.id;
                        return (
                          <button
                            key={p.id}
                            onClick={() => handleSwitchProvider(p.id)}
                            className={`px-2 py-0.5 rounded-md text-[11px] font-medium transition ${
                              active
                                ? 'bg-[#EC0000] text-white'
                                : 'text-zinc-400 hover:text-zinc-200'
                            }`}
                            title={`${p.label} (${p.sub})`}
                          >
                            {p.label}
                          </button>
                        );
                      })}
                    </div>

                    <div className="h-3 w-[1px] bg-white/[0.07] mx-0.5" />

                    {/* Subtle Slash Chips */}
                    {SLASH_COMMANDS.map((sc) => (
                      <button
                        key={sc.cmd}
                        onClick={() => setInput((prev) => `${sc.cmd} ${prev}`.trim())}
                        title={sc.desc}
                        className="px-2 py-0.5 rounded-md hover:bg-white/[0.06] text-[11px] font-mono text-zinc-500 hover:text-zinc-300 transition shrink-0"
                      >
                        {sc.cmd}
                      </button>
                    ))}
                  </div>

                  {/* Right: Send Button */}
                  <button
                    onClick={handleSendMessage}
                    disabled={isStreaming || !input.trim()}
                    className="w-7 h-7 rounded-lg bg-[#EC0000] hover:bg-[#D40000] disabled:opacity-25 disabled:hover:bg-[#EC0000] text-white flex items-center justify-center transition shrink-0"
                    title="Enviar (Enter)"
                  >
                    <ArrowUp className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>

        {/* Slide-Over Right Drawer: File Preview & Background Processes */}
        {rightDrawerOpen && (
          <aside className="w-[460px] border-l border-white/[0.07] bg-[#0C0C0E] flex flex-col shrink-0 shadow-2xl animate-drawer-left select-text">
            <div className="h-11 px-4 border-b border-white/[0.06] flex items-center justify-between">
              <div className="flex items-center gap-1 bg-white/[0.04] p-0.5 rounded-lg text-xs">
                <button
                  onClick={() => setRightTab('file')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition ${
                    rightTab === 'file'
                      ? 'bg-white/[0.1] text-white'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  Vista Previa {previewFile ? `(${previewFile.name})` : ''}
                </button>
                <button
                  onClick={() => setRightTab('activity')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition ${
                    rightTab === 'activity'
                      ? 'bg-white/[0.1] text-white'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  Procesos ({runtimeStatus.subagents.length + runtimeStatus.tasks.length})
                </button>
              </div>

              <button
                onClick={() => setRightDrawerOpen(false)}
                className="p-1 rounded-lg hover:bg-white/[0.05] text-zinc-400 hover:text-white transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {rightTab === 'file' ? (
              <div className="flex-1 flex flex-col overflow-hidden">
                {previewFile ? (
                  <>
                    <div className="px-4 py-2.5 border-b border-white/[0.06] bg-[#0F0F13] flex items-center justify-between">
                      <div className="truncate">
                        <div className="text-xs font-mono font-medium text-white">
                          {previewFile.name}
                        </div>
                        <div className="text-[10px] font-mono text-zinc-500 truncate">
                          {previewFile.path}
                        </div>
                      </div>
                      <button
                        onClick={() =>
                          setInput((prev) => `${prev} @${previewFile.name} `.trimStart())
                        }
                        className="px-2 py-1 rounded-md bg-white/[0.06] hover:bg-white/[0.12] text-[11px] text-zinc-200 font-mono shrink-0 transition"
                      >
                        @ Mencionar
                      </button>
                    </div>
                    <pre className="flex-1 overflow-auto p-4 text-xs font-mono text-zinc-200 leading-relaxed bg-[#09090B]">
                      <code>{previewFile.content}</code>
                    </pre>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center p-8 text-center text-xs text-zinc-500">
                    Selecciona un archivo de texto, CSV o Playbook en la barra izquierda para previsualizarlo aquí. Los archivos Excel y PowerPoint se abren directamente en su aplicación de Office al hacerles clic.
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-4 space-y-5 text-xs">
                <div>
                  <div className="text-[10px] font-medium uppercase tracking-wider text-zinc-500 mb-2">
                    Subagentes ({runtimeStatus.subagents.length})
                  </div>
                  {runtimeStatus.subagents.length === 0 ? (
                    <div className="text-zinc-600">Sin subagentes en ejecución.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {runtimeStatus.subagents.map((sa: any) => (
                        <div
                          key={sa.conversation_id}
                          className="p-3 rounded-xl border border-white/[0.06] bg-[#111115] flex items-center justify-between"
                        >
                          <div>
                            <div className="text-zinc-200 font-medium">{sa.role}</div>
                            <div className="text-[11px] font-mono text-zinc-500">
                              {sa.conversation_id} · {sa.type_name}
                            </div>
                          </div>
                          <span className="text-[11px] font-mono text-emerald-400">
                            {sa.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div className="text-[10px] font-medium uppercase tracking-wider text-zinc-500 mb-2">
                    Terminales en Background ({runtimeStatus.tasks.length})
                  </div>
                  {runtimeStatus.tasks.length === 0 ? (
                    <div className="text-zinc-600">Sin procesos activos.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {runtimeStatus.tasks.map((t: any) => (
                        <div
                          key={t.task_id}
                          className="p-3 rounded-xl border border-white/[0.06] bg-[#111115] space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-zinc-200 font-medium">{t.tool_summary}</span>
                            <span className="text-[11px] font-mono text-zinc-400">{t.status}</span>
                          </div>
                          <div className="text-[11px] font-mono text-zinc-500 truncate">
                            {t.command_line}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div className="text-[10px] font-medium uppercase tracking-wider text-zinc-500 mb-2">
                    Cron & Timers ({runtimeStatus.schedules.length})
                  </div>
                  {runtimeStatus.schedules.length === 0 ? (
                    <div className="text-zinc-600">Sin tareas programadas.</div>
                  ) : (
                    <div className="space-y-1.5">
                      {runtimeStatus.schedules.map((job: any) => (
                        <div
                          key={job.job_id}
                          className="p-3 rounded-xl border border-white/[0.06] bg-[#111115]"
                        >
                          <div className="text-zinc-200">{job.prompt}</div>
                          <div className="text-[11px] font-mono text-zinc-500 mt-0.5">
                            {job.job_id} · {job.status}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </aside>
        )}
      </div>

      {/* Modals */}
      <CredentialsModal
        isOpen={credModalOpen}
        onClose={() => setCredModalOpen(false)}
        credentials={credentials}
        windowsTargets={windowsTargets}
        onSaveSecret={async (key, secret, customTarget) => {
          await fetch(`${ENGINE_HTTP}/api/credentials`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, secret, custom_target: customTarget }),
          });
          await fetchCredentials();
        }}
        onLinkTarget={async (key, targetName) => {
          await fetch(`${ENGINE_HTTP}/api/credentials/link-target`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, target_name: targetName }),
          });
          await fetchCredentials();
        }}
        onDeleteSecret={async (key) => {
          await fetch(`${ENGINE_HTTP}/api/credentials/${key}`, { method: 'DELETE' });
          await fetchCredentials();
        }}
        onRefresh={fetchCredentials}
      />

      <SettingsAndMCPModal
        isOpen={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        config={config}
        onUpdateConfig={async (patch) => {
          const updated = await fetch(`${ENGINE_HTTP}/api/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(patch),
          }).then((r) => r.json());
          setConfig(updated);
          await fetchRuntimeStatus();
        }}
      />

      <WorkspaceModal
        isOpen={workspaceModalOpen}
        onClose={() => setWorkspaceModalOpen(false)}
        currentWorkspace={workspacePath}
        savedProjects={config?.saved_projects || []}
        onSelectWorkspace={handleSelectWorkspace}
        onRemoveSavedProject={handleRemoveSavedProject}
        engineHttp={ENGINE_HTTP}
      />
    </div>
  );
}
