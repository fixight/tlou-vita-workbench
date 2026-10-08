// Pure camera math shared by playback and CPU-only regression checks.
export function verticalFov(horizontalDegrees, aspect) {
    return 2 * Math.atan(Math.tan(horizontalDegrees * Math.PI / 360) / aspect) * 180 / Math.PI;
}

export function horizontalFov(focalLength, defaultBlend) {
    const denominator = focalLength > 0 ? 2 * focalLength : 46.916;
    const angle = 2 * Math.atan2(36, denominator) * 180 / Math.PI;
    const weight = Math.max(0, Math.min(1, defaultBlend));
    return angle * (1 - weight) + 75 * weight;
}

export function sampleLens(track, frame, blend) {
    if (!track.lens) return {fov: track.fov_degrees, axis: track.fov_axis || 'vertical'};
    const samples = track.lens.samples;
    const index = Math.min(Math.floor(frame), samples.length - 1);
    const before = samples[index], after = samples[Math.min(index + 1, samples.length - 1)];
    const mix = (a, b) => a + (b - a) * blend;
    const dof = track.lens.depth_of_field?.samples;
    return {
        fov: horizontalFov(mix(before[1], after[1]), mix(before[2], after[2])), axis: 'horizontal',
        focalLength: mix(before[1], after[1]),
        depthOfField: dof ? dof[index].map((v, n) => mix(v, dof[Math.min(index + 1, dof.length - 1)][n])) : null,
    };
}

export function cameraBlend(track, index, fraction) {
    const samples = track.lens?.samples;
    if (!samples) return fraction;
    const before = samples[index][3], after = samples[Math.min(index + 1, samples.length - 1)][3];
    const marker = before + (after - before) * fraction;
    // Original PS4 sampler uses these thresholds and selects the next frame.
    return Math.abs(before - after) > .4 && marker > .00001 && marker < .99999 ? 1 : fraction;
}
