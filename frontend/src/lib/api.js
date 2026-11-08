async function request(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const post = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export const api = {
  board: () => request("/api/board"),
  rescuer: (id) => request(`/api/rescuer/${id}`),
  assign: (id, teamId) => post(`/api/tickets/${id}/assign`, { team_id: teamId }),
  field: (id, status) => post(`/api/tickets/${id}/field`, { status }),
  takeOver: (id) => post(`/api/tickets/${id}/take-over`),
  startShift: () => post("/api/shift/start"),
  say: (text, lang) => post("/api/voice/say", { text, lang }),
  operatorStart: () => post("/api/operator/calls"),
  operatorEnd: (id) => post(`/api/operator/calls/${id}/end`),
  operatorTurn: (id, wavBlob, speaker) =>
    request(`/api/operator/calls/${id}/turn?speaker=${speaker}&filename=turn.wav`, {
      method: "POST", headers: { "Content-Type": "audio/wav" }, body: wavBlob,
    }),
  saveNotes: (id, text) => request(`/api/tickets/${id}/notes`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ operator_notes: text }),
  }),
  checkNotes: (id, text) => post(`/api/tickets/${id}/notes/check`, { operator_notes: text }),
  simCallerReply: (id, facts, lang) => post(`/api/sim/${id}/caller-reply`, { facts, lang }),
  startVoiceCall: () => post("/api/voice/calls"),
  dropCall: (id) => post(`/api/calls/${id}/drop`),
  voiceTurn: (id, wavBlob) =>
    request(`/api/voice/calls/${id}/turn?filename=turn.wav`, {
      method: "POST", headers: { "Content-Type": "audio/wav" }, body: wavBlob,
    }),
};
