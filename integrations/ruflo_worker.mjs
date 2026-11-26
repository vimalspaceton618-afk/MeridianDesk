import { readFileSync } from 'node:fs';
import { AgentRegistry } from './ruflo-dist/coordination/agent-registry.js';
import { TaskOrchestrator } from './ruflo-dist/coordination/task-orchestrator.js';
import { EventBus } from './ruflo-dist/shared/events.js';

const { symbol, bars } = JSON.parse(readFileSync(0, 'utf8'));
const returns = bars.slice(1).map((bar, i) => bar.close / bars[i].close - 1);
const pct = n => (n * 100).toFixed(3) + '%';
const bus = new EventBus();
const agents = new AgentRegistry(bus);
const scheduler = new TaskOrchestrator(bus, agents);
const jobs = new Map();
const outputs = new Map();

function schedule(agent, title, run, dependencies = []) {
    agents.register({ id: agent, role: 'worker', domain: 'core', description: title,
        capabilities: [{name: title, description: title, supportedTaskTypes: ['analysis']}],
        dependencies: [], priority: 1 });
    const task = scheduler.createTask({type: 'analysis', title, description: title, domain: 'core',
        phase: 'implementation', priority: 'medium', dependencies});
    scheduler.queueTask(task.id);
    jobs.set(task.id, {agent, run});
    return task.id;
}

const path = schedule('drawdown', 'Drawdown analyst', () => {
    let peak = bars[0].close, worst = 0;
    for (const bar of bars) {
        peak = Math.max(peak, bar.close);
        worst = Math.max(worst, 1 - bar.close / peak);
    }
    return { worst, current: 1 - bars.at(-1).close / peak };
});
const dispersion = schedule('volatility', 'Volatility analyst', () => {
    const mean = returns.reduce((sum, x) => sum + x, 0) / returns.length;
    const variance = returns.reduce((sum, x) => sum + (x - mean) ** 2, 0) / (returns.length - 1);
    return Math.sqrt(variance);
});
const tail = schedule('tail-loss', 'Tail-loss analyst', () => {
    const ordered = returns.map(x => -x).sort((a, b) => b - a);
    const count = Math.ceil(ordered.length * .05);
    return { count, total: ordered.length, mean: ordered.slice(0, count).reduce((s, x) => s+x, 0)/count };
});
const review = schedule('review', 'Risk reviewer', () => {
    const dd = outputs.get(path), vol = outputs.get(dispersion), loss = outputs.get(tail);
    return [
        symbol + ' | Ruflo risk review',
        bars.length + ' bars ending ' + new Date(bars.at(-1).time * 1000).toISOString(),
        'Peak-to-trough drawdown ' + pct(dd.worst) + ' | currently below peak by ' + pct(dd.current),
        'Historical per-bar volatility ' + pct(vol) + ' (sample standard deviation)',
        'Average loss in worst ' + loss.count + ' of ' + loss.total + ' observed one-bar returns: ' + pct(loss.mean),
        'The drawdown uses closing prices. Tail losses describe this sample; the worst future loss may be larger.',
    ].join('\n');
}, [path, dispersion, tail]);

for (const job of jobs.values()) await agents.spawn(job.agent);
while (true) {
    const next = scheduler.getNextTask();
    if (!next) break;
    const job = jobs.get(next.id);
    scheduler.assignTask(next.id, job.agent);
    scheduler.startTask(next.id);
    const started = performance.now();
    const output = job.run();
    outputs.set(next.id, output);
    scheduler.completeTask(next.id, {taskId:next.id, success:true, output, duration:performance.now()-started});
}
if (scheduler.getTask(review).status !== 'completed') throw new Error('Review dependencies did not complete.');
console.log(outputs.get(review));
console.log('Ruflo completed ' + scheduler.getTasksByStatus('completed').length + ' assigned tasks.');
