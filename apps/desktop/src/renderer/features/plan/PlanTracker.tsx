import React, { useEffect, useState } from 'react'
import type { Plan, PlanStep } from '../../../shared/ipc'

const statusIcon: Record<string, string> = {
  pending: '⬜',
  in_progress: '🔄',
  completed: '✅',
  skipped: '⏭️',
}

export default function PlanTracker() {
  const [plan, setPlan] = useState<Plan | null>(null)

  useEffect(() => {
    const unsub = window.miqi.plan.onUpdated((data) => {
      setPlan(data.plan)
    })
    return () => { unsub() }
  }, [])

  if (!plan) {
    return (
      <div className="p-4">
        <h2 className="text-lg font-bold mb-2">Plan</h2>
        <p className="text-gray-400 text-sm">No active plan. The agent creates plans for complex tasks.</p>
      </div>
    )
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-bold mb-2">Plan: {plan.title}</h2>
      <div className="space-y-2">
        {plan.steps.map((step: PlanStep) => (
          <div
            key={step.id}
            className={`p-2 rounded border ${
              step.status === 'in_progress' ? 'border-blue-400 bg-blue-50 dark:bg-blue-900' :
              step.status === 'completed' ? 'border-green-400 bg-green-50 dark:bg-green-900' :
              'border-gray-200'
            }`}
          >
            <span className="mr-2">{statusIcon[step.status] || '❓'}</span>
            <span className="text-sm">{step.description}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
