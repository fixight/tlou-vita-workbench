// Preview sequencing only: original script waits are not inferred here.
export function buildTimeline(stages) {
    let duration = 0;
    const entries = stages.map((stage, index) => {
        if (!Number.isFinite(stage.duration) || stage.duration <= 0) {
            throw new Error(`Invalid duration for cinematic stage ${index}`);
        }
        const start = duration;
        duration += stage.duration;
        return {index, start, end: duration};
    });
    if (!entries.length) throw new Error('Empty cinematic timeline');
    return {entries, duration};
}

export function locateTime(timeline, value) {
    if (!Number.isFinite(value)) throw new Error('Invalid cinematic time');
    const absolute = Math.max(0, Math.min(value, timeline.duration));
    const entry = timeline.entries.find(entry => absolute < entry.end)
        ?? timeline.entries.at(-1);
    return {index: entry.index, local: absolute - entry.start, absolute};
}
