import React, { useState, useEffect } from 'react';
import { Package, ToggleLeft, ToggleRight, Trash2, Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

interface PluginInfo {
  name: string;
  version: string;
  description: string;
  status: 'active' | 'disabled' | 'error';
  scope: string;
}

export function PluginMarket() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const result = await window.miqi.plugins.list();
      setPlugins((result as unknown as { plugins: PluginInfo[] })?.plugins || []);
    } catch {
      /* ignore */
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const handleToggle = async (name: string, currentStatus: string) => {
    try {
      await window.miqi.plugins.toggle(name, currentStatus !== 'active');
      await load();
    } catch (e) {
      console.error(e);
    }
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`Uninstall ${name}?`)) return;
    try {
      await window.miqi.plugins.uninstall(name);
      await load();
    } catch (e) {
      console.error(e);
    }
  };

  if (loading)
    return (
      <div className="p-4 flex items-center gap-2">
        <Loader2 className="animate-spin" size={16} /> Loading...
      </div>
    );

  return (
    <div className="p-4 max-w-2xl">
      <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
        <Package size={20} /> Plugin Market
      </h2>
      {plugins.length === 0 ? (
        <p className="text-gray-400">
          No plugins installed. Add plugins to ~/.miqi/plugins/ or &lt;workspace&gt;/.miqi/plugins/.
        </p>
      ) : (
        <div className="space-y-3">
          {plugins.map((p) => (
            <div key={p.name} className="border rounded p-3 bg-white dark:bg-gray-800">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium">{p.name}</span>
                  <span className="text-xs text-gray-400 ml-2">v{p.version}</span>
                  <span
                    className={cn(
                      'ml-2 text-xs px-1.5 py-0.5 rounded',
                      p.status === 'active'
                        ? 'bg-green-100 text-green-700'
                        : p.status === 'error'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-gray-100 text-gray-600'
                    )}
                  >
                    {p.status}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleToggle(p.name, p.status)}
                    className="text-[var(--text-muted)] hover:text-[var(--text)]"
                  >
                    {p.status === 'active' ? (
                      <ToggleRight size={18} className="text-green-500" />
                    ) : (
                      <ToggleLeft size={18} />
                    )}
                  </button>
                  <button
                    onClick={() => handleUninstall(p.name)}
                    className="text-red-400 hover:text-red-600"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              {p.description && <p className="text-xs text-gray-500 mt-1">{p.description}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
