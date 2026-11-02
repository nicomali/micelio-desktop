import React, { useEffect, useState } from 'react';
import {
  ArrowUpLeft,
  Check,
  ChevronRight,
  Folder,
  FolderOpen,
  HardDrive,
  X,
} from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  currentWorkspace: string;
  onSelectWorkspace: (newPath: string) => Promise<void>;
  engineHttp: string;
}

export const WorkspaceModal: React.FC<Props> = ({
  isOpen,
  onClose,
  currentWorkspace,
  onSelectWorkspace,
  engineHttp,
}) => {
  const [currentDir, setCurrentDir] = useState(currentWorkspace);
  const [parentDir, setParentDir] = useState<string | null>(null);
  const [folders, setFolders] = useState<Array<{ name: string; path: string }>>([]);
  const [quickRoots, setQuickRoots] = useState<Array<{ label: string; path: string }>>([]);
  const [manualPath, setManualPath] = useState(currentWorkspace);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setManualPath(currentWorkspace);
      void loadDir(currentWorkspace);
    }
  }, [isOpen, currentWorkspace]);

  const loadDir = async (dirPath?: string) => {
    setLoading(true);
    try {
      const q = dirPath ? `?path=${encodeURIComponent(dirPath)}` : '';
      const res = await fetch(`${engineHttp}/api/workspace/browse${q}`).then((r) => r.json());
      setCurrentDir(res.current || '');
      setManualPath(res.current || '');
      setParentDir(res.parent || null);
      setFolders(res.folders || []);
      setQuickRoots(res.quick_roots || []);
    } finally {
      setLoading(false);
    }
  };

  const handleNativeDialogIfElectron = async () => {
    const anyWin = window as any;
    if (anyWin.micelioElectron?.pickDirectory) {
      const picked = await anyWin.micelioElectron.pickDirectory();
      if (picked) {
        await onSelectWorkspace(picked);
        onClose();
      }
    }
  };

  if (!isOpen) return null;

  const hasNativePicker = Boolean((window as any).micelioElectron?.pickDirectory);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4">
      <div className="w-full max-w-xl rounded-2xl border border-white/[0.08] bg-[#111114] shadow-2xl overflow-hidden flex flex-col max-h-[82vh] animate-modal-pop">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#EC0000]/10 border border-[#EC0000]/25 flex items-center justify-center text-[#EC0000]">
              <FolderOpen className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">Seleccionar Workspace</h2>
              <p className="text-xs text-zinc-400">
                Elige la carpeta del repositorio o proyecto donde trabajará Micelio
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/[0.06] text-zinc-400 hover:text-white transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Quick Roots + Native Button */}
        <div className="px-5 py-2.5 border-b border-white/[0.05] bg-white/[0.01] flex items-center justify-between gap-2 overflow-x-auto">
          <div className="flex items-center gap-1.5">
            {quickRoots.map((qr) => (
              <button
                key={qr.path}
                onClick={() => loadDir(qr.path)}
                className="px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.09] border border-white/[0.06] text-[11px] text-zinc-300 flex items-center gap-1.5 transition"
              >
                <HardDrive className="w-3 h-3 text-zinc-400" />
                <span>{qr.label}</span>
              </button>
            ))}
          </div>

          {hasNativePicker && (
            <button
              onClick={handleNativeDialogIfElectron}
              className="px-2.5 py-1 rounded-lg bg-[#EC0000]/15 hover:bg-[#EC0000]/25 border border-[#EC0000]/30 text-[11px] text-[#FF5555] font-medium transition shrink-0"
            >
              Explorador de Windows...
            </button>
          )}
        </div>

        {/* Manual Path Bar */}
        <div className="px-5 py-3 border-b border-white/[0.05] flex items-center gap-2">
          {parentDir && (
            <button
              onClick={() => loadDir(parentDir)}
              className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] text-zinc-300 transition"
              title="Subir un nivel"
            >
              <ArrowUpLeft className="w-3.5 h-3.5" />
            </button>
          )}
          <input
            type="text"
            value={manualPath}
            onChange={(e) => setManualPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                void loadDir(manualPath);
              }
            }}
            placeholder="C:/ruta/a/tu/proyecto"
            className="flex-1 px-3 py-1.5 rounded-lg bg-[#0B0B0D] border border-white/[0.07] text-xs font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          />
          <button
            onClick={() => loadDir(manualPath)}
            className="px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-xs text-zinc-200 transition"
          >
            Ir
          </button>
        </div>

        {/* Folder Browser List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-0.5 min-h-[240px]">
          {loading ? (
            <div className="p-6 text-center text-xs text-zinc-500 animate-shimmer">
              Cargando directorios...
            </div>
          ) : folders.length === 0 ? (
            <div className="p-6 text-center text-xs text-zinc-500">
              No hay subcarpetas en <span className="font-mono text-zinc-300">{currentDir}</span>. Puedes seleccionar esta carpeta directamente abajo.
            </div>
          ) : (
            folders.map((f) => (
              <button
                key={f.path}
                onClick={() => loadDir(f.path)}
                className="w-full text-left px-3 py-2 rounded-xl hover:bg-white/[0.05] text-xs text-zinc-200 flex items-center justify-between group transition"
              >
                <span className="flex items-center gap-2.5 truncate">
                  <Folder className="w-4 h-4 text-[#EC0000]/80 group-hover:text-[#EC0000] transition shrink-0" />
                  <span className="truncate">{f.name}</span>
                </span>
                <ChevronRight className="w-3.5 h-3.5 text-zinc-600 group-hover:text-zinc-300 group-hover:translate-x-0.5 transition-all" />
              </button>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3.5 border-t border-white/[0.06] bg-[#0D0D10] flex items-center justify-between gap-3">
          <div className="text-[11px] font-mono text-zinc-400 truncate">
            Seleccionado: <span className="text-zinc-200">{manualPath}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg hover:bg-white/[0.05] text-zinc-400 text-xs transition"
            >
              Cancelar
            </button>
            <button
              onClick={async () => {
                await onSelectWorkspace(manualPath);
                onClose();
              }}
              className="px-4 py-1.5 rounded-lg bg-[#EC0000] hover:bg-[#D40000] active:scale-[0.98] text-white text-xs font-medium flex items-center gap-1.5 transition"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Abrir este Workspace</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
