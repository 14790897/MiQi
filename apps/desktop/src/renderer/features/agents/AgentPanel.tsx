import React, { useEffect, useState } from 'react';
import type { LiveAgentInfo } from '../../../shared/ipc';

export default function AgentPanel() {
  const [agents, setAgents] = useState<LiveAgentInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await window.miqi.agents.list();
        setAgents(result.agents || []);
      } catch (e) {
        console.error('Failed to load agents:', e);
      } finally {
        setLoading(false);
      }
    };
    load();
    const unsub = window.miqi.agents.onSpawned(() => load());
    return () => {
      unsub();
    };
  }, []);

  const statusColor = (s: string) => {
    switch (s) {
      case 'idle':
        return 'bg-gray-400';
      case 'thinking':
        return 'bg-yellow-400 animate-pulse';
      case 'executing':
        return 'bg-blue-400 animate-pulse';
      case 'completed':
        return 'bg-green-500';
      case 'error':
        return 'bg-red-500';
      case 'aborted':
        return 'bg-orange-500';
      default:
        return 'bg-gray-400';
    }
  };

  if (loading) return <div className="p-4">Loading agents...</div>;

  return (
    <div className="p-4">
      <h2 className="text-lg font-bold mb-4">智能体</h2>
      {agents.length === 0 ? (
        <p className="text-gray-400">暂无运行中的智能体，发送消息即可启动。</p>
      ) : (
        <div className="space-y-3">
          {agents.map((a) => (
            <div key={a.agent_id} className="border rounded p-3 bg-white dark:bg-gray-800">
              <div className="flex items-center gap-2">
                <span className={`w-3 h-3 rounded-full ${statusColor(a.status)}`} />
                <span className="font-medium">{a.type}</span>
                <span className="text-sm text-gray-500">({a.status})</span>
              </div>
              <p className="text-sm text-gray-600 mt-1">{a.label}</p>
              <p className="text-xs text-gray-400">ID: {a.agent_id}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
