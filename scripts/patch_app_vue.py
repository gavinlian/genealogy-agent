from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src" / "App.vue"
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

new_block = """    <main v-if="!showOCR" class="main" :class="{ 'main--workspace': workspaceLayout === 'classic' && !!currentFamily, 'main--agent-chat': workspaceLayout === 'chat' }">
      <FamilyChatShell
        v-if="workspaceLayout === 'chat'"
        :family="currentFamily"
        :families="families"
        :families-loading="loading"
        @select-family="viewFamily"
        @leave-family="clearCurrentFamily"
        @switch-classic="enterClassicWorkspace"
        @refresh="onChatShellRefresh"
        @create-family="showCreateModal = true"
        @scan="goOCR"
        @settings="showSettings = true"
        @delete-family="requestDeleteFamily"
      />

      <!-- 经典编辑（次要） -->
"""

# Keep line 0-1 (<template> and app-shell), drop header+home+old shell (lines 2-57), keep from classic section (line 58+)
out = lines[:2] + [new_block] + lines[58:]
path.write_text("".join(out), encoding="utf-8")
print("patched", path)
