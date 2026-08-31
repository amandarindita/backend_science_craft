import os

api_keys_file = r"D:\Antigravityackend_science_craft	emplatesdminpi_keys.html"

with open(api_keys_file, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Clean the label in table
old_label = """                    <td class="py-3.5 px-3 font-semibold text-slate-800">
                        <div class="flex items-center space-x-2">
                            <span>${k.label}</span>
                            ${k.provider === 'elevenlabs' && k.voice_id ? `<span class="inline-flex items-center space-x-1 text-[10px] font-mono bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded-md" title="Voice ID: ${k.voice_id}"><i data-lucide="mic" class="w-3 h-3"></i><span>${k.voice_id.slice(0, 8)}...</span></span>` : ''}
                        </div>
                        ${errorNote}
                    </td>"""

new_label = """                    <td class="py-3.5 px-3 font-semibold text-slate-800">
                        ${k.label}
                        ${errorNote}
                    </td>"""

if old_label in content:
    content = content.replace(old_label, new_label)

# 2. Add Edit button to action column
old_actions = """                    <td class="py-3.5 px-3 text-right space-x-1">
                        <!-- Test Button -->"""

new_actions = """                    <td class="py-3.5 px-3 text-right space-x-1">
                        <!-- Edit Button -->
                        <button onclick="openEditModal(${k.id})" 
                                title="Edit Detail / Ganti Key"
                                class="p-1.5 rounded-lg text-slate-600 hover:bg-slate-100 border border-slate-200 transition-colors">
                            <i data-lucide="edit-3" class="w-4 h-4"></i>
                        </button>

                        <!-- Test Button -->"""

if old_actions in content and "openEditModal" not in content:
    content = content.replace(old_actions, new_actions)

# 3. Add Edit Modal HTML before endblock
edit_modal_html = """
<!-- MODAL EDIT / DETAIL API KEY -->
<div id="edit-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 hidden">
    <div class="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 border border-slate-200 transform transition-all">
        <div class="flex items-center justify-between pb-4 border-b border-slate-100">
            <div class="flex items-center space-x-2">
                <div class="w-8 h-8 rounded-lg bg-sky-100 text-sky-600 flex items-center justify-center">
                    <i data-lucide="edit-3" class="w-4 h-4"></i>
                </div>
                <h3 class="font-bold text-slate-900 text-base">Edit & Detail API Key</h3>
            </div>
            <button onclick="closeEditModal()" class="text-slate-400 hover:text-slate-600">
                <i data-lucide="x" class="w-5 h-5"></i>
            </button>
        </div>

        <form id="form-edit-key" onsubmit="submitEditKey(event)" class="mt-5 space-y-4">
            <input type="hidden" id="edit-key-id">
            <input type="hidden" id="edit-provider">

            <div>
                <label class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">Layanan AI (Provider)</label>
                <div id="edit-provider-badge" class="inline-flex items-center px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-100 text-slate-800">
                    -
                </div>
            </div>

            <div>
                <label class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">Label / Nama Akun</label>
                <input type="text" id="edit-label" required placeholder="Nama Akun"
                       class="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-sky-500 focus:outline-none text-sm">
            </div>

            <div>
                <label class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5 flex items-center justify-between">
                    <span>Ganti API Key String</span>
                    <span class="text-[10px] text-slate-400 font-normal">Kosongkan jika tidak diubah</span>
                </label>
                <input type="text" id="edit-key-value" placeholder="Biarkan kosong jika tidak ingin mengubah key"
                       class="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-sky-500 focus:outline-none text-sm font-mono text-xs">
            </div>

            <!-- Voice ID (ElevenLabs Only) -->
            <div id="edit-voice-id-wrapper" class="hidden">
                <label class="block text-xs font-semibold text-indigo-700 uppercase tracking-wider mb-1.5 flex items-center justify-between">
                    <span>Voice ID Kloning (VoiceLab)</span>
                    <span class="text-[10px] bg-indigo-100 text-indigo-800 font-bold px-2 py-0.5 rounded-md">ElevenLabs Only</span>
                </label>
                <input type="text" id="edit-voice-id" placeholder="Misal: 4UNmeS5ijruDobVfcjih"
                       class="w-full px-3.5 py-2.5 rounded-xl border border-indigo-200 focus:ring-2 focus:ring-indigo-500 focus:outline-none text-sm font-mono text-xs bg-indigo-50/30">
                <p class="text-[11px] text-slate-400 mt-1">ID suara kloning tutor untuk akun ini.</p>
            </div>

            <div class="pt-4 flex justify-end space-x-3">
                <button type="button" onclick="closeEditModal()"
                        class="px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors">
                    Batal
                </button>
                <button type="submit" id="btn-submit-edit"
                        class="px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-sky-600 hover:bg-sky-700 shadow-md shadow-sky-600/20 transition-all flex items-center space-x-1.5">
                    <span>Simpan Perubahan</span>
                </button>
            </div>
        </form>
    </div>
</div>
{% endblock %}"""

if "{% endblock %}" in content and "id="edit-modal"" not in content:
    content = content.replace("{% endblock %}", edit_modal_html, 1)

# 4. Add JS functions for Edit Modal
edit_js = """
    // MODAL EDIT
    function openEditModal(keyId) {
        const allKeys = [...globalKeysData.gemini, ...globalKeysData.elevenlabs];
        const key = allKeys.find(k => k.id === keyId);
        if (!key) return;

        document.getElementById('edit-key-id').value = key.id;
        document.getElementById('edit-provider').value = key.provider;
        document.getElementById('edit-label').value = key.label;
        document.getElementById('edit-key-value').value = '';

        const badge = document.getElementById('edit-provider-badge');
        const voiceWrapper = document.getElementById('edit-voice-id-wrapper');

        if (key.provider === 'gemini') {
            badge.innerText = "Google Gemini API";
            badge.className = "inline-flex items-center px-3 py-1.5 rounded-xl text-xs font-bold bg-sky-100 text-sky-800";
            voiceWrapper.classList.add('hidden');
        } else {
            badge.innerText = "ElevenLabs Text-to-Speech";
            badge.className = "inline-flex items-center px-3 py-1.5 rounded-xl text-xs font-bold bg-indigo-100 text-indigo-800";
            voiceWrapper.classList.remove('hidden');
            document.getElementById('edit-voice-id').value = key.voice_id || '';
        }

        document.getElementById('edit-modal').classList.remove('hidden');
    }

    function closeEditModal() {
        document.getElementById('edit-modal').classList.add('hidden');
        document.getElementById('form-edit-key').reset();
    }

    async function submitEditKey(e) {
        e.preventDefault();
        const keyId = document.getElementById('edit-key-id').value;
        const label = document.getElementById('edit-label').value;
        const key_value = document.getElementById('edit-key-value').value;
        const voice_id = document.getElementById('edit-voice-id').value.trim();
        const submitBtn = document.getElementById('btn-submit-edit');

        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span>Menyimpan...</span>`;

        try {
            const res = await fetch(`/admin/web/api/keys/${keyId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label, key_value, voice_id })
            });
            const data = await res.json();

            if (data.success) {
                showToast(data.message, 'success');
                closeEditModal();
                fetchKeys();
            } else {
                showToast(data.error || "Gagal memperbarui key", 'error');
            }
        } catch (e) {
            showToast("Terjadi kesalahan sistem", 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `<span>Simpan Perubahan</span>`;
        }
    }
"""

if "function openEditModal" not in content:
    content = content.replace("    // Init fetch", edit_js + "
    // Init fetch")

with open(api_keys_file, "w", encoding="utf-8") as f:
    f.write(content)

print("api_keys.html updated successfully!")
