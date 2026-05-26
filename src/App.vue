<template>
  <div class="app-shell">
    <header v-if="!showOCR && workspaceLayout === 'classic' && !currentFamily" class="app-header">
      <div class="header-brand">
        <div class="logo-mark">族</div>
        <div>
          <h1>族见</h1>
          <p class="header-tagline">见家族，见自己</p>
        </div>
      </div>
      <div class="header-actions">
        <button v-if="!currentFamily" class="btn-scan" @click="goOCR">扫描建谱</button>
        <button class="btn-icon" title="AI 设置" @click="showSettings = true">⚙</button>
      </div>
    </header>

    <main v-if="!showOCR" class="main" :class="{ 'main--workspace': workspaceLayout === 'classic' && !!currentFamily, 'main--agent-chat': workspaceLayout === 'chat' }">
      <FamilyChatShell
        v-if="workspaceLayout === 'chat'"
        :family="currentFamily"
        :families="families"
        :families-loading="loading"
        @select-family="viewFamily"
        @leave-family="leaveFamilyFromChat"
        @switch-classic="enterClassicWorkspace"
        @refresh="onChatShellRefresh"
        @create-family="showCreateModal = true"
        @scan="goOCR"
        @settings="showSettings = true"
        @delete-family="requestDeleteFamily"
      />

      <!-- 经典编辑（次要） -->
      <section v-if="currentFamily && workspaceLayout === 'classic'" class="section main--workspace">
        <div class="workspace-toolbar">
          <div class="workspace-toolbar-title">
            <button class="btn-back" @click="leaveFamily">← 返回</button>
            <h2>
              {{ currentFamily.name }}
              <span v-if="currentFamily.surname" class="surname-tag">{{ currentFamily.surname }}氏</span>
            </h2>
            <span class="stat-chip stat-chip--inline"><strong>{{ persons.length }}</strong> 人</span>
            <span v-if="maxGeneration" class="stat-chip stat-chip--inline"><strong>{{ maxGeneration }}</strong> 代</span>
          </div>
          <div class="toolbar-mobile-quick">
            <button type="button" class="btn-primary btn-sm" @click="openAddPerson">+ 新增</button>
            <button
              type="button"
              class="btn-secondary btn-sm"
              :class="{ 'btn-ghost': !showTextImportDrawer }"
              @click="showTextImportDrawer = !showTextImportDrawer"
            >
              原文{{ sourceVersionBadge }}
            </button>
            <button
              type="button"
              class="btn-secondary btn-sm"
              :class="{ 'btn-ghost': !showOrganizeDrawer }"
              @click="showOrganizeDrawer = !showOrganizeDrawer"
            >
              整理<span v-if="pendingOrganizePlan && planHasChanges(pendingOrganizePlan)" class="toolbar-badge">1</span>
            </button>
            <button type="button" class="btn-secondary btn-sm" @click="workspaceLayout = 'chat'">对话</button>
            <button type="button" class="btn-secondary btn-sm" @click="openAiOrganize()">AI</button>
            <button
              type="button"
              class="btn-secondary btn-sm"
              :class="{ 'btn-ghost': !showMobileToolbarMenu }"
              @click="showMobileToolbarMenu = !showMobileToolbarMenu"
            >
              {{ showMobileToolbarMenu ? '收起' : '更多' }}
            </button>
          </div>
          <div class="workspace-toolbar-actions" :class="{ 'toolbar-actions-expanded': showMobileToolbarMenu }">
            <span class="stat-chip toolbar-stat-desktop"><strong>{{ persons.length }}</strong> 人</span>
            <span v-if="maxGeneration" class="stat-chip toolbar-stat-desktop"><strong>{{ maxGeneration }}</strong> 代</span>
            <span class="toolbar-divider toolbar-stat-desktop"></span>
            <button class="btn-primary btn-sm" @click="openAddPerson">+ 新增人物</button>
            <button class="btn-secondary btn-sm" @click="importFile?.click()">导入</button>
            <button class="btn-secondary btn-sm" @click="showExportDrawer = !showExportDrawer">导出</button>
            <button class="btn-secondary btn-sm" :class="{ 'btn-ghost': !showSearchDrawer }" @click="showSearchDrawer = !showSearchDrawer">搜索</button>
            <button class="btn-secondary btn-sm" @click="backupFamilyLocal">备份</button>
            <button
              class="btn-secondary btn-sm"
              :class="{ 'btn-ghost': !showTextImportDrawer }"
              @click="showTextImportDrawer = !showTextImportDrawer"
            >
              原文{{ sourceVersionBadge }}
            </button>
            <button class="btn-secondary btn-sm" @click="showRelationsDrawer = !showRelationsDrawer">关系</button>
            <button class="btn-ghost btn-sm" @click="openFamilyEdit">编辑族谱</button>
            <button class="btn-secondary btn-sm" :class="{ 'btn-ghost': !showOrganizeDrawer }" @click="showOrganizeDrawer = !showOrganizeDrawer">
              族谱整理<span v-if="pendingOrganizePlan && planHasChanges(pendingOrganizePlan)" class="toolbar-badge">1</span>
            </button>
            <button class="btn-secondary btn-sm" @click="workspaceLayout = 'chat'">对话模式</button>
            <button class="btn-secondary btn-sm" @click="openAiOrganize()" title="与 AI 对话，获取关系整理建议">
              AI 整理
            </button>
            <button class="btn-ghost btn-sm" @click="rebuildFamily" :disabled="buildLoading || !persons.length" title="对比原文差异后补全关系">
              {{ buildLoading ? '整理中…' : '快速整理' }}
            </button>
            <button class="btn-scan btn-sm" @click="goOCRFromFamily">扫描</button>
            <button class="btn-icon" title="设置" @click="showSettings = true">⚙</button>
          </div>
        </div>

        <div v-if="showTextImportDrawer" class="workspace-drawer ocr-text-drawer workspace-drawer--text">
          <div v-if="sourceVersions.length" class="source-version-bar">
            <label class="source-version-label">原文版本</label>
            <select
              v-model="currentSourceVersionId"
              class="input input-inline source-version-select"
              @change="onSourceVersionSelect"
            >
              <option v-for="v in sourceVersions" :key="v.id" :value="v.id">
                {{ versionOptionLabel(v) }}
              </option>
            </select>
            <span v-if="currentSourceVersion?.status === 'confirmed'" class="source-version-tag confirmed">已确认</span>
            <span v-else class="source-version-tag draft">草稿</span>
            <button type="button" class="btn-xs" :disabled="sourceVersions.length < 2" @click="compareSourceVersions">
              版本对比
            </button>
            <button type="button" class="btn-xs" :disabled="!ocrEditableText.trim()" @click="saveAsNewSourceVersion">
              另存为…
            </button>
            <button
              type="button"
              class="btn-xs btn-primary"
              :disabled="!currentSourceVersionId || currentSourceVersion?.status === 'confirmed'"
              @click="confirmCurrentSourceVersion"
            >
              确认此版
            </button>
            <button
              type="button"
              class="btn-xs btn-danger"
              :disabled="!currentSourceVersionId || sourceVersions.length <= 1"
              title="至少保留一个原文版本"
              @click="deleteCurrentSourceVersion"
            >
              删除此版
            </button>
          </div>
          <p v-if="sourceVersionDiff?.summary" class="hint source-version-diff-summary">{{ sourceVersionDiff.summary }}</p>
          <pre v-if="sourceVersionDiff?.diff_lines?.length" class="source-version-diff-pre">{{ sourceVersionDiff.diff_lines.slice(0, 80).join('\n') }}</pre>
          <p class="hint" style="margin:0 0 8px">
            三版文字：版本一 OCR 原文（对应图片）→ 版本二 AI 关系描述（可组谱）→ 版本三 您的修正稿。组谱默认用版本二；确认版本三后可切换为定稿。
          </p>
          <OcrTextWorkspace
            v-model="ocrEditableText"
            v-model:annotations="ocrAnnotations"
            :preview-persons="parsedPersons"
            :preview-relations="parsedRelations"
            :structured-text="ocrRelationDescription || ocrEditableText"
            :view-title="currentFamily?.name || '族谱'"
            :relation-link-from="relationLinkFromName"
            compact
            @add-person="addAnnotatedPersonToFamily"
            @set-link-from="relationLinkFromName = $event"
            @create-link="createRelationFromNames"
            @clear-link="relationLinkFromName = null"
          />
          <div class="text-drawer-actions">
            <button class="btn-xs" :disabled="!ocrEditableText.trim()" @click="saveFamilySourceText">
              保存原文
            </button>
            <button class="btn-xs btn-primary" :disabled="syncPersonDetailsLoading || !persons.length || !activeSourceText.trim()" @click="syncPersonDetailsFromSource">
              {{ syncPersonDetailsLoading ? '补全中…' : '从文字版补全成员资料' }}
            </button>
            <button class="btn-xs btn-primary" :disabled="ocrReparsing || !ocrEditableText.trim()" @click="applyTextParseToFamily">
              {{ ocrReparsing ? '两阶段解析中…' : '两阶段解析并对比差异' }}
            </button>
            <button
              type="button"
              class="btn-xs btn-secondary"
              :disabled="!ocrEditableText.trim()"
              @click="openAiOrganize({ bootstrap: true })"
            >
              改用 AI 对话整理
            </button>
            <button v-if="relationLinkFromName" class="btn-xs" @click="relationLinkFromName = null">取消连线</button>
          </div>
          <div v-if="textParseFailedHint" class="source-parse-fallback-hint">
            <span>{{ textParseFailedHint }}</span>
            <button type="button" class="btn-xs btn-primary" @click="openAiOrganize({ bootstrap: true })">
              打开 AI 对话整理
            </button>
          </div>
          <div v-if="pendingTextRelations.length" class="pending-relations-box">
            <strong>待确认关系（{{ pendingTextRelations.length }}）</strong>
            <ul>
              <li v-for="(r, i) in pendingTextRelations" :key="'ptr'+i">
                {{ r.from }} → {{ r.to }}
                <button class="btn-xs" @click="applySingleTextRelation(r)">应用</button>
              </li>
            </ul>
          </div>
        </div>

        <div v-if="showSearchDrawer" class="workspace-drawer">
          <div class="search-box">
            <select v-model="searchMode" class="input input-inline">
              <option value="keyword">关键词</option>
              <option value="nl">智能问法</option>
            </select>
            <input
              v-model="searchQuery"
              class="input"
              :placeholder="searchMode === 'nl' ? '如：张三的弟弟、第3代' : '姓名 / 世代 / 字号 / 简介'"
              @keyup.enter="doSearchAndSelect"
            />
            <button class="btn-primary btn-sm" @click="doSearchAndSelect">搜索</button>
          </div>
          <p v-if="searchMode === 'nl'" class="hint">支持：某人的 父亲/母亲/儿子/兄弟/配偶；第N代</p>
          <div v-if="searchLoading" class="loading">搜索中…</div>
          <div v-else class="persons-list" style="margin-top:12px">
            <div
              v-for="r in searchResults"
              :key="r.id"
              class="person-card"
              style="cursor:pointer"
              @click="selectPerson(r.id)"
            >
              <div class="person-info">
                <h4>{{ r.name }}</h4>
                <p>{{ r.match_reason }} · 第{{ r.generation || '?' }}代 {{ r.generation_name || '' }}</p>
              </div>
            </div>
            <div v-if="searchResults.length === 0 && searchQuery" class="empty-hint">无匹配成员</div>
          </div>
        </div>

        <div v-if="showExportDrawer" class="workspace-drawer">
          <div class="export-grid">
            <button type="button" class="export-card" @click="exportJSON">
              <span class="export-card-icon">📥</span>
              <span class="export-card-title">导出 JSON</span>
              <p class="export-card-desc">完整数据备份，可再次导入</p>
            </button>
            <button type="button" class="export-card" @click="exportPDF">
              <span class="export-card-icon">📄</span>
              <span class="export-card-title">导出 PDF</span>
              <p class="export-card-desc">浏览器打印为纸质族谱</p>
            </button>
            <button type="button" class="export-card" @click="importFile?.click()">
              <span class="export-card-icon">📤</span>
              <span class="export-card-title">导入 JSON</span>
              <p class="export-card-desc">从备份文件恢复族谱</p>
            </button>
          </div>
          <input type="file" ref="importFile" @change="handleImport" accept=".json" style="display:none"/>
        </div>

        <GenealogyOrganizePanel
          v-if="showOrganizeDrawer && currentFamily"
          :family-id="currentFamily.id"
          :member-count="persons.length"
          :selected-person-id="selectedPersonId || undefined"
          :selected-person-name="displayPerson?.name || ''"
          :source-version-id="currentSourceVersionId || undefined"
          :source-version-label="currentSourceVersion?.label || ''"
          v-model:apply-mode="organizeApplyMode"
          v-model:clean-slate="organizeCleanSlate"
          :plan="pendingOrganizePlan"
          :diff="pendingOrganizeDiff"
          @update:plan="onOrganizePlanPatch"
          @plan-edited="onOrganizePlanEdited"
          @applied="onOrganizeApplied"
          @cleared="onOrganizeCleared"
          @open-ai-chat="openAiOrganize()"
          @dismiss="dismissOrganizePlan"
          @notify="(msg, type) => showToast(msg, type || 'info')"
        />

        <div v-if="showRelationsDrawer" class="workspace-drawer">
          <div class="relation-editor">
            <h4>添加关系</h4>
            <div class="relation-form-row">
              <select v-model="newRelation.from_person_id" class="input">
                <option value="">选择成员（父/夫）</option>
                <option v-for="p in persons" :key="'f'+p.id" :value="p.id">{{ p.name }}（第{{ p.generation || '?' }}代）</option>
              </select>
              <span class="relation-arrow">→</span>
              <select v-model="newRelation.to_person_id" class="input">
                <option value="">选择成员（子/妻）</option>
                <option v-for="p in persons" :key="'t'+p.id" :value="p.id">{{ p.name }}（第{{ p.generation || '?' }}代）</option>
              </select>
            </div>
            <div class="relation-form-row">
              <select v-model="newRelation.relation_type" class="input input-inline">
                <option value="parent_child">父子/母子</option>
                <option value="spouse">配偶</option>
              </select>
              <select v-model="newRelation.status" class="input input-inline">
                <option value="confirmed">已确认</option>
                <option value="inferred">待确认</option>
                <option value="disputed">有争议</option>
              </select>
              <button class="btn-primary btn-sm" @click="addRelation">添加</button>
            </div>
          </div>
          <div class="relations-list" style="margin-top:12px">
            <div v-for="r in relations" :key="r.id" class="relation-row">
              <span>{{ r.from_name || '?' }} → {{ r.to_name || '?' }}</span>
              <span class="rel-type">{{ relationTypeLabel(r.relation_type) }}</span>
              <button class="btn-xs btn-danger" @click="removeRelation(r.id)">删除</button>
            </div>
          </div>
        </div>

        <button
          type="button"
          class="nav-mobile-toggle"
          @click="mobileNavOpen = !mobileNavOpen"
        >
          {{ mobileNavOpen ? '收起世代导航' : '展开世代导航' }}
          <span class="nav-mobile-toggle-count">{{ persons.length }} 人</span>
        </button>

        <div class="workspace-body">
          <!-- 左侧树状导航 -->
          <aside class="workspace-nav" :class="{ 'nav-mobile-open': mobileNavOpen }">
            <div class="workspace-nav-header">世代导航</div>
            <div class="workspace-nav-list">
              <template v-for="item in flatNavItems" :key="item.id">
                <div class="nav-tree-item" :class="{ active: selectedPersonId === item.id }" :style="{ paddingLeft: (8 + item.depth * 14) + 'px' }">
                  <button
                    v-if="item.hasChildren"
                    type="button"
                    class="nav-tree-toggle"
                    @click.stop="toggleNavExpand(item.id)"
                  >{{ item.expanded ? '▼' : '▶' }}</button>
                  <span v-else class="nav-tree-toggle placeholder"></span>
                  <button type="button" class="nav-tree-name" @click="selectPersonFromNav(item.id)">{{ item.name }}</button>
                  <span v-if="item.generation" class="nav-tree-gen">{{ item.generation }}代</span>
                </div>
              </template>
              <div v-if="!flatNavItems.length" class="empty-hint" style="padding:12px">暂无成员</div>
            </div>
          </aside>

          <!-- 中间：参考 App 两种族谱阅读样式 -->
          <div class="workspace-canvas workspace-canvas--reference">
            <div class="canvas-toolbar canvas-toolbar--reference">
              <div class="ocr-view-mode-group" role="tablist" aria-label="族谱样式">
                <button
                  type="button"
                  role="tab"
                  class="ocr-view-mode-btn"
                  :class="{ active: genealogyViewMode === 'page' }"
                  @click="genealogyViewMode = 'page'"
                >
                  谱页 · 右起世系
                </button>
                <button
                  type="button"
                  role="tab"
                  class="ocr-view-mode-btn"
                  :class="{ active: genealogyViewMode === 'card' }"
                  @click="genealogyViewMode = 'card'"
                >
                  卡片 · 竖排世代
                </button>
              </div>
              <span v-if="buildStats" class="hint canvas-stats-hint">
                {{ buildStats.person_count }} 人 · {{ buildStats.relation_count }} 关系
              </span>
              <span class="toolbar-divider canvas-stats-hint"></span>
              <button type="button" class="btn-xs" title="缩小" @click="referenceZoomOut">−</button>
              <span class="canvas-zoom-label">{{ referenceZoomLabel }}</span>
              <button type="button" class="btn-xs" title="放大" @click="referenceZoomIn">+</button>
              <button type="button" class="btn-xs" @click="referenceFitView">适应</button>
              <button type="button" class="btn-xs" @click="referenceZoomReset">100%</button>
            </div>
            <GenealogyReferenceViewport
              v-if="persons.length"
              ref="referenceViewportRef"
              :mode="genealogyViewMode"
              :persons="persons"
              :relations="relations"
              :structured-text="activeSourceText"
              :title="currentFamily?.name || '族谱'"
              :selected-person-id="selectedPersonId"
              @select="selectPersonFromReference"
            />
            <div v-if="persons.length" class="canvas-touch-controls">
              <button type="button" class="canvas-touch-btn" aria-label="放大" @click="referenceZoomIn">+</button>
              <button type="button" class="canvas-touch-btn canvas-touch-btn--fit" aria-label="适应" @click="referenceFitView">⊡</button>
              <button type="button" class="canvas-touch-btn" aria-label="缩小" @click="referenceZoomOut">−</button>
            </div>
            <div v-else class="empty-state workspace-reference-empty">
              <div class="empty-icon">🌳</div>
              <h3>族谱还是空的</h3>
              <p>扫描老族谱或手动添加第一位祖先</p>
              <button class="btn-primary btn-sm" @click="openAddPerson">添加成员</button>
            </div>
          </div>

          <!-- 右侧详情面板 -->
          <div
            v-if="detailMobileOpen"
            class="detail-mobile-backdrop"
            @click="closeDetailMobile"
          ></div>
          <aside class="workspace-detail" :class="{ 'detail-mobile-open': detailMobileOpen }">
            <div class="detail-header">
              <h3>{{ displayPerson?.name || '成员详情' }}</h3>
              <div class="detail-header-actions">
                <button v-if="displayPerson" class="btn-primary btn-sm" @click="editPerson(displayPerson)">编辑</button>
                <button type="button" class="btn-close detail-close-btn" aria-label="关闭详情" @click="closeDetailMobile">×</button>
              </div>
            </div>
            <div v-if="!displayPerson" class="detail-body detail-empty">
              <p>在左侧「世代导航」或中间<strong>谱页 / 卡片</strong>中点击成员，查看详情</p>
              <p class="hint">谱页：右起世系竖排 · 卡片：按代竖排姓名</p>
            </div>
            <div v-else class="detail-body">
              <div class="detail-field">
                <label>姓名</label>
                <p>{{ displayPerson.name }} <span class="gender-tag">{{ genderLabel(displayPerson.gender) }}</span></p>
              </div>
              <div v-if="displayPerson.generation" class="detail-field">
                <label>世代</label>
                <p>第 {{ displayPerson.generation }} 世<span v-if="displayPerson.generation_name"> · {{ displayPerson.generation_name }}</span></p>
              </div>
              <div v-if="displayPerson.birth_year || displayPerson.death_year" class="detail-field">
                <label>生卒</label>
                <p>
                  {{ displayPerson.birth_year || '?' }}
                  –
                  {{ displayPerson.death_year || '今' }}
                </p>
              </div>
              <div v-if="displayPerson.courtesy_name || displayPerson.art_name" class="detail-field">
                <label>字 / 号</label>
                <p>{{ displayPerson.courtesy_name || '—' }} / {{ displayPerson.art_name || '—' }}</p>
              </div>
              <div v-if="displayPerson.location_text || displayPerson.county" class="detail-field">
                <label>籍贯</label>
                <p>{{ displayPerson.location_text || [displayPerson.county, displayPerson.town, displayPerson.village].filter(Boolean).join(' ') }}</p>
              </div>
              <div v-if="displayPerson.biography" class="detail-field">
                <label>简介</label>
                <p>{{ displayPerson.biography }}</p>
              </div>
              <div v-if="selectedPersonSourceExcerpt" class="detail-field detail-field--source">
                <label>原文 / 文字版摘录</label>
                <pre class="detail-source-excerpt">{{ selectedPersonSourceExcerpt }}</pre>
              </div>
              <p
                v-if="!displayPerson.biography && !displayPerson.birth_year && !displayPerson.death_year && !selectedPersonSourceExcerpt"
                class="hint detail-no-meta-hint"
              >
                结构化字段尚空。请先在上方保存文字版，再点「从文字版补全成员资料」；或使用「快速整理」一并补关系与资料。
              </p>
              <div v-if="parentName(displayPerson.parent_id)" class="detail-field">
                <label>父母</label>
                <p>
                  <a href="#" @click.prevent="selectPerson(displayPerson.parent_id)">{{ parentName(displayPerson.parent_id) }}</a>
                </p>
              </div>
              <div v-if="spouseName(displayPerson.spouse_id)" class="detail-field">
                <label>配偶</label>
                <p>
                  <a href="#" @click.prevent="selectPerson(displayPerson.spouse_id!)">{{ spouseName(displayPerson.spouse_id) }}</a>
                </p>
              </div>
              <div class="detail-relations">
                <h4>关联关系</h4>
                <div v-for="rel in selectedPersonRelations" :key="rel.id" class="detail-rel-row detail-rel-row-editable">
                  <a href="#" class="detail-rel-link" @click.prevent="selectPerson(rel.otherId)">{{ rel.label }}</a>
                  <span class="detail-rel-type">{{ rel.typeLabel }}</span>
                  <button type="button" class="btn-xs btn-danger" @click="removeRelation(rel.id)">删</button>
                </div>
                <div v-if="!selectedPersonRelations.length" class="hint">暂无关联关系（可点工具栏「连线」在图中建立）</div>
              </div>
              <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn-xs" @click="addChild(displayPerson)">+ 子女</button>
                <button class="btn-xs" @click="addKinship(displayPerson, '孙')">+ 孙</button>
                <button class="btn-xs" @click="addKinship(displayPerson, '曾孙')">+ 曾孙</button>
                <button class="btn-xs btn-danger" @click="deletePerson(displayPerson.id)">删除</button>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>

      <!-- 设置页 -->
    <div v-if="showSettings" class="modal">
      <div class="modal-content modal-lg ai-settings-modal">
        <div class="ai-settings-header">
          <h3>AI 设置</h3>
          <button class="btn-close" @click="showSettings = false">×</button>
        </div>

        <p class="settings-hint">
          MiniMax 需填写 <strong>API Key</strong> 和 <strong>Group ID</strong>（控制台 → 基础信息）。
          Group ID 会放在请求头 <code>GroupId</code> 里发送。
        </p>

        <div class="provider-tabs">
          <div
            v-for="p in providers"
            :key="p.id"
            :class="['tab-item', { active: keyTab === p.id }]"
            @click="keyTab = p.id"
          >
            <span class="tab-name">{{ providerLabel(p) }}</span>
            <span v-if="providerKeys[p.id]?.configured" class="tab-dot"></span>
            <span v-if="p.is_free" class="tab-badge">免费</span>
          </div>
        </div>

        <div class="settings-group">
          <label>{{ providerLabel(activeProvider) }} API Key</label>
          <input
            v-if="providerKeys[keyTab]"
            v-model="providerKeys[keyTab].api_key"
            type="password"
            :placeholder="providerKeys[keyTab]?.configured ? '已保存，输入新 Key 可覆盖' : '输入 API Key'"
            class="input"
          />
          <input
            v-if="keyTab === 'minimax' && providerKeys[keyTab]"
            v-model="providerKeys[keyTab].group_id"
            type="text"
            placeholder="Group ID（控制台基础信息，必填）"
            class="input"
          />
          <input
            v-if="keyTab === 'custom' && providerKeys[keyTab]"
            v-model="providerKeys[keyTab].api_base"
            type="text"
            placeholder="API Base URL"
            class="input"
          />
          <div class="test-row">
            <button class="btn-test" :disabled="testStatus.key.loading" @click="testAIModel('key')">
              {{ testStatus.key.loading ? '测试中…' : '测试 API Key' }}
            </button>
          </div>
          <div
            v-if="testStatus.key.loading || testStatus.key.message"
            class="test-banner"
            :class="testStatus.key.loading ? 'pending' : (testStatus.key.ok ? 'ok' : 'fail')"
          >
            <template v-if="testStatus.key.loading">正在连接 {{ providerLabel(activeProvider) }}…</template>
            <template v-else>
              {{ testStatus.key.ok ? '✓' : '✗' }} {{ testStatus.key.message }}
              <span v-if="testStatus.key.latency" class="test-latency">（{{ testStatus.key.latency }}ms）</span>
            </template>
          </div>
          <p v-if="testStatus.key.preview && !testStatus.key.loading" class="test-preview">模型回复：{{ testStatus.key.preview }}</p>
        </div>

        <div class="model-row">
          <span class="model-label">OCR 识别</span>
          <select v-model="ocrConfig.provider" class="input input-inline" @change="onOcrProviderChange">
            <option v-for="p in visionProviders" :key="p.id" :value="p.id">{{ providerLabel(p) }}</option>
          </select>
          <select v-if="ocrModelOptions.length" v-model="ocrConfig.model" class="input input-inline">
            <option v-for="m in ocrModelOptions" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-else v-model="ocrConfig.model" class="input input-inline" placeholder="模型名称"/>
          <button class="btn-test" :disabled="testStatus.ocr.loading" @click="testAIModel('ocr')">
            {{ testStatus.ocr.loading ? '测试中…' : '测试' }}
          </button>
        </div>
        <p v-if="testStatus.ocr.message" :class="['test-result', 'test-result-block', testStatus.ocr.ok ? 'ok' : 'fail']">
          OCR：{{ testStatus.ocr.ok ? '✓' : '✗' }} {{ testStatus.ocr.message }}
          <template v-if="testStatus.ocr.latency">（{{ testStatus.ocr.latency }}ms）</template>
          <span v-if="testStatus.ocr.preview" class="test-preview-inline"> – {{ testStatus.ocr.preview }}</span>
        </p>

        <div class="model-row">
          <span class="model-label">关系解析（初步分析）</span>
          <select v-model="parseConfig.provider" class="input input-inline" @change="onParseProviderChange">
            <option v-for="p in providers" :key="p.id" :value="p.id">{{ providerLabel(p) }}</option>
          </select>
          <select v-if="parseModelOptions.length" v-model="parseConfig.model" class="input input-inline">
            <option v-for="m in parseModelOptions" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-else v-model="parseConfig.model" class="input input-inline" placeholder="模型名称"/>
          <button class="btn-test" :disabled="testStatus.parse.loading" @click="testAIModel('parse')">
            {{ testStatus.parse.loading ? '测试中…' : '测试' }}
          </button>
        </div>
        <p v-if="testStatus.parse.message" :class="['test-result', 'test-result-block', testStatus.parse.ok ? 'ok' : 'fail']">
          解析：{{ testStatus.parse.ok ? '✓' : '✗' }} {{ testStatus.parse.message }}
          <template v-if="testStatus.parse.latency">（{{ testStatus.parse.latency }}ms）</template>
          <span v-if="testStatus.parse.preview" class="test-preview-inline"> – {{ testStatus.parse.preview }}</span>
        </p>

        <div class="modal-actions">
          <button class="btn-secondary" @click="showSettings = false">取消</button>
          <button class="btn-primary" @click="saveAISettings">保存</button>
        </div>
      </div>
    </div>

    <!-- OCR 扫描全流程 -->
    <div v-if="showOCR" class="ocr-overlay">
      <div class="ocr-panel">
        <div class="ocr-header">
          <button class="btn-back" @click="showOCR = false; currentFamily = null">← 返回</button>
          <h2>扫描建谱</h2>
          <button class="btn-icon" @click="showSettings = true">⚙</button>
        </div>

        <div class="ocr-steps">
          <div class="ocr-step-dot" :class="{ active: ocrStep === 'select' || !ocrStep, done: ocrStep !== 'select' && ocrStep }"></div>
          <div class="ocr-step-dot" :class="{ active: ocrStep === 'upload', done: ocrStep === 'result' }"></div>
          <div class="ocr-step-dot" :class="{ active: ocrStep === 'result' }"></div>
        </div>

        <div class="ocr-container">
          <!-- 选择族谱 -->
          <div v-if="!ocrStep || ocrStep === 'select'" class="ocr-step">
            <p class="hint">选择要录入的族谱</p>
            <div class="family-select">
              <div v-for="f in families" :key="f.id" class="family-option" @click="selectFamilyForOCR(f)">
                <h4>{{ f.name }}</h4>
                <p>{{ f.person_count || 0 }} 位成员</p>
              </div>
            </div>
            <button class="btn-secondary" @click="showCreateModal = true; showOCR = false">+ 新建族谱</button>
          </div>

          <!-- 上传图片 -->
          <div v-if="ocrStep === 'upload'" class="ocr-step">
            <p class="hint">上传族谱照片（支持拍照或相册）</p>
            <div class="upload-box" @click="fileInput?.click()">
              <div v-if="!previewImage">
                <div class="upload-icon">📷</div>
                <p>点击拍照/选择照片</p>
              </div>
              <img v-else :src="previewImage" class="preview-image"/>
            </div>
            <input type="file" ref="fileInput" @change="handleImageSelect" accept="image/*" style="display:none" />

            <div v-if="ocrLoading" class="loading">正在识别图片文字…</div>
            <p v-if="previewImage && !ocrLoading" class="ocr-model-hint">
              OCR: {{ providerLabel(getProvider(ocrConfig.provider)) }} / {{ ocrConfig.model }}
              · 解析: {{ providerLabel(getProvider(parseConfig.provider)) }} / {{ parseConfig.model }}
            </p>

            <div class="ocr-actions">
              <button v-if="previewImage && !ocrLoading" class="btn-primary" @click="doOCR">开始识别</button>
            </div>
          </div>

          <!-- 识别结果 -->
          <div v-if="ocrStep === 'result'" class="ocr-step ocr-step-result">
            <div class="ocr-result-layout">
              <div class="ocr-result-left">
                <div v-if="ocrDescribingV2" class="ocr-describing-banner" role="status">
                  <span class="ocr-describing-spinner" aria-hidden="true"></span>
                  版本一已识别完成，正在详细整理人物关系…
                </div>
                <div class="ocr-version-tabs">
                  <button type="button" class="ocr-version-tab" :class="{ active: ocrVersionTab === 'v1' }" @click="ocrVersionTab = 'v1'">
                    版本一 · OCR 原文
                  </button>
                  <button type="button" class="ocr-version-tab" :class="{ active: ocrVersionTab === 'v2' }" @click="ocrVersionTab = 'v2'">
                    版本二 · 关系描述
                  </button>
                  <button type="button" class="ocr-version-tab" :class="{ active: ocrVersionTab === 'v3' }" @click="ocrVersionTab = 'v3'">
                    版本三 · 修正稿
                  </button>
                </div>
                <p v-if="ocrVersionTab === 'v1'" class="hint ocr-version-hint">对应扫描图片的忠实 OCR 转写，可标注姓名、可编辑。</p>
                <p v-else-if="ocrVersionTab === 'v2'" class="hint ocr-version-hint">AI 从版本一整理的关系描述稿，用于数字化组谱（可重新生成）。</p>
                <p v-else class="hint ocr-version-hint">您的手工修正（可与原文无关）；保存后可用于对比与定稿。</p>

                <div v-show="ocrVersionTab === 'v1'">
                  <OcrTextWorkspace
                    v-model="ocrEditableText"
                    v-model:annotations="ocrAnnotations"
                    :preview-persons="parsedPersons"
                    :preview-relations="parsedRelations"
                    :structured-text="ocrRelationDescription || ocrEditableText"
                    view-title="扫描识别"
                    :image-preview="previewImage"
                    :relation-link-from="relationLinkFromName"
                    @add-person="addAnnotatedPersonToParsed"
                    @set-link-from="relationLinkFromName = $event"
                    @create-link="createRelationFromNames"
                    @clear-link="relationLinkFromName = null"
                  />
                </div>

                <div v-show="ocrVersionTab === 'v2'" class="ocr-version-editor">
                  <div class="ocr-relation-desc-header">
                    <strong>版本二 · 关系描述稿</strong>
                    <span v-if="ocrParseSteps.length" class="hint">流程：{{ ocrParseSteps.join(' → ') }}</span>
                  </div>
                  <div v-if="ocrDescribingV2 && !ocrRelationDescription.trim()" class="ocr-describing-placeholder">
                    <span class="ocr-describing-spinner" aria-hidden="true"></span>
                    正在根据版本一整理人物关系，请稍候…
                  </div>
                  <textarea
                    v-else
                    v-model="ocrRelationDescription"
                    class="input ocr-version-textarea"
                    rows="14"
                    placeholder="扫描完成后自动生成；也可从版本一重新生成"
                  />
                  <div class="ocr-relation-desc-actions">
                    <button
                      type="button"
                      class="btn-xs btn-secondary"
                      :disabled="ocrRegeneratingV2 || ocrDescribingV2 || !ocrEditableText.trim()"
                      @click="regenerateOcrV2"
                    >
                      {{ ocrRegeneratingV2 ? '生成中…' : '从版本一重新生成' }}
                    </button>
                    <button type="button" class="btn-xs" @click="copyRelationDescription">复制</button>
                  </div>
                </div>

                <div v-show="ocrVersionTab === 'v3'" class="ocr-version-editor">
                  <div class="ocr-relation-desc-header">
                    <strong>版本三 · 修正稿</strong>
                    <button type="button" class="btn-xs" @click="initCustomFromV2">从版本二复制</button>
                  </div>
                  <textarea
                    v-model="ocrCustomText"
                    class="input ocr-version-textarea"
                    rows="14"
                    placeholder="在此修正 OCR 错误或补充关系；可与版本一无关"
                  />
                </div>

                <div class="ocr-reparse-row">
                  <button
                    class="btn-secondary btn-sm"
                    :disabled="ocrReparsing || ocrDescribingV2 || !digitizeSourceText.trim()"
                    @click="reparseFromEditedText"
                  >
                    {{ ocrReparsing ? '数字化解析中…' : '从组谱用文字解析入库预览' }}
                  </button>
                  <span class="hint">优先版本三 → 版本二 → 版本一</span>
                </div>
              </div>

              <div class="ocr-result-right">
            <div v-if="ocrDescribingV2 && !genealogyStats" class="ocr-describing-placeholder ocr-describing-placeholder-compact">
              <span class="ocr-describing-spinner" aria-hidden="true"></span>
              正在整理人物关系并生成族谱预览…
            </div>

            <div v-if="scanValidation && scanValidation.issue_count > 0" class="validation-box">
              <p>数据校验（{{ scanValidation.error_count }} 错误 / {{ scanValidation.warning_count }} 警告）</p>
              <ul>
                <li v-for="(issue, i) in scanValidation.issues" :key="i" :class="issue.level">
                  {{ issue.person ? issue.person + '：' : '' }}{{ issue.message }}
                </li>
              </ul>
            </div>

            <div v-if="genealogyStats" class="genealogy-stats-box">
              <strong>自动族谱整理</strong>
              {{ genealogyStats.person_count }} 人 · {{ genealogyStats.relation_count }} 条关系 · {{ genealogyStats.generation_count }} 代
              · 树根 {{ genealogyStats.root_count || 0 }} 个
            </div>

            <p v-if="treePreviewNodes.length" class="hint">族谱树预览（{{ treePreviewNodes.length }} 节点）：</p>
            <div v-if="treePreviewNodes.length" class="tree-preview-mini">
              <span v-for="n in treePreviewNodes.slice(0, 24)" :key="n.id" class="preview-node" :style="{ marginLeft: (n.depth || 0) * 12 + 'px' }">
                {{ n.name }}<span v-if="n.generation" class="preview-gen">（{{ n.generation }}代）</span>
              </span>
              <span v-if="treePreviewNodes.length > 24" class="hint">…共 {{ treePreviewNodes.length }} 人</span>
            </div>

            <p v-if="parsedRelations.length">关系（{{ parsedRelations.length }} 条，入库时一并保存）：</p>
            <ul v-if="parsedRelations.length" class="relation-preview">
              <li v-for="(r, i) in parsedRelations" :key="'rel'+i">
                {{ r.from }} → {{ r.to }}
                <span class="rel-status" :class="r.status || 'inferred'">{{ r.status || '待确认' }}</span>
              </li>
            </ul>

            <p>待入库成员（拖入姓名标签或点击标签添加）：</p>
            <div
              class="parsed-list parsed-list-drop"
              :class="{ 'drag-over': parsedListDragOver }"
              @dragover.prevent="onParsedListDragOver"
              @dragleave="parsedListDragOver = false"
              @drop="onParsedListDrop"
            >
              <div
                v-for="(p, i) in parsedPersons"
                :key="i"
                class="parsed-person"
                :class="{ 'needs-review': p.review_status && p.review_status !== 'confirmed' }"
              >
                <div class="parsed-info">
                  <strong>{{ p.name }}</strong>
                  <span>{{ p.gender === 'male' ? '男' : p.gender === 'female' ? '女' : '未知' }}</span>
                  <span v-if="p.birth_year">{{ p.birth_year }}年{{ p.death_year ? '-' + p.death_year + '年' : '' }}</span>
                  <span v-if="p.generation">第{{ p.generation }}代</span>
                </div>
                <div class="parsed-actions">
                  <button class="btn-xs" @click="editParsedPerson(i)">编辑</button>
                  <button class="btn-xs btn-danger" @click="parsedPersons.splice(i, 1)">删除</button>
                </div>
              </div>
              <p v-if="!parsedPersons.length" class="hint" style="padding:12px;text-align:center">将左侧姓名标签拖入此处</p>
            </div>
              </div>
            </div>

            <p class="hint" style="margin-top:8px">保存后进入族谱工作区，可在左侧导航或右侧详情面板继续调整。</p>
            <div class="ocr-actions">
              <button class="btn-secondary" @click="ocrStep = 'upload'">重新上传</button>
              <button
                class="btn-primary"
                :disabled="!ocrEditableText.trim() && !parsedPersons.length"
                @click="saveParsedPersons"
              >
                保存到族谱{{ ocrEditableText.trim() ? '（含原文）' : '' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建族谱弹窗 -->
    <div v-if="showCreateModal" class="modal">
      <div class="modal-content">
        <h3>创建族谱</h3>
        <input v-model="newFamily.name" placeholder="族谱名称" class="input"/>
        <input v-model="newFamily.surname" placeholder="姓氏" class="input"/>
        <textarea v-model="newFamily.description" placeholder="简介" class="input"></textarea>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showCreateModal = false">取消</button>
          <button class="btn-primary" @click="createFamily">创建</button>
        </div>
      </div>
    </div>

    <!-- 编辑族谱 -->
    <div v-if="showFamilyModal" class="modal">
      <div class="modal-content">
        <h3>编辑族谱</h3>
        <input v-model="familyForm.name" placeholder="族谱名称" class="input"/>
        <input v-model="familyForm.surname" placeholder="姓氏" class="input"/>
        <textarea v-model="familyForm.description" placeholder="简介" class="input"></textarea>
        <div class="form-section">
          <label class="form-label">代际起点</label>
          <div class="form-row-2">
            <input
              v-model.number="familyForm.start_generation"
              type="number"
              min="1"
              placeholder="起始代数（默认 1）"
              class="input"
            />
            <select v-model="familyForm.root_person_id" class="input">
              <option value="">自动识别始祖</option>
              <option v-for="p in persons" :key="'root'+p.id" :value="p.id">
                {{ p.name }}（第{{ p.generation || '?' }}代）
              </option>
            </select>
          </div>
          <p class="hint">始祖记为第 {{ familyForm.start_generation || 1 }} 代；修改后将自动重算全谱世代。</p>
          <button type="button" class="btn-xs" @click="recalculateGenerations">立即重算世代</button>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="showFamilyModal = false">取消</button>
          <button class="btn-primary" @click="saveFamily">保存</button>
        </div>
      </div>
    </div>

    <!-- 添加/编辑人物弹窗 -->
    <div v-if="showPersonModal" class="modal">
      <div class="modal-content modal-lg person-editor-modal">
        <div class="ai-settings-header">
          <h3>{{ editingPerson?.id ? '编辑成员' : '添加成员' }}</h3>
          <button class="btn-close" @click="showPersonModal = false">×</button>
        </div>

        <div class="form-section">
          <label class="form-label required">基本信息</label>
          <input
            v-model="personForm.name"
            placeholder="姓名（必填）"
            class="input"
            :class="{ 'input-error': personFormErrors.name }"
          />
          <p v-if="personFormErrors.name" class="field-error">{{ personFormErrors.name }}</p>
          <div class="form-row-2">
            <select v-model="personForm.gender" class="input">
              <option value="unknown">性别未知</option>
              <option value="male">男</option>
              <option value="female">女</option>
            </select>
            <input v-model.number="personForm.generation" placeholder="世代" class="input" type="number"/>
          </div>
          <div class="form-row-2">
            <input
              v-model.number="personForm.birth_year"
              placeholder="出生年"
              class="input"
              type="number"
              :class="{ 'input-error': personFormErrors.birth_year }"
            />
            <input
              v-model.number="personForm.death_year"
              placeholder="去世年（空=在世）"
              class="input"
              type="number"
              :class="{ 'input-error': personFormErrors.death_year }"
            />
          </div>
          <p v-if="personFormErrors.birth_year" class="field-error">{{ personFormErrors.birth_year }}</p>
          <p v-if="personFormErrors.death_year" class="field-error">{{ personFormErrors.death_year }}</p>
          <input v-model="personForm.generation_name" placeholder="字辈" class="input"/>
        </div>

        <div class="form-section">
          <label class="form-label">家族关系</label>
          <select v-model="personForm.parent_id" class="input">
            <option value="">无父母（作始祖或待关联）</option>
            <option v-for="p in parentCandidates" :key="'par'+p.id" :value="p.id">
              {{ p.name }}（第{{ p.generation || '?' }}代）
            </option>
          </select>
          <select v-model="personForm.spouse_id" class="input">
            <option value="">无配偶</option>
            <option v-for="p in spouseCandidates" :key="'sp'+p.id" :value="p.id">
              {{ p.name }}（第{{ p.generation || '?' }}代）
            </option>
          </select>
          <select v-if="editingPerson?.id" v-model="personForm.review_status" class="input">
            <option value="confirmed">数据已确认</option>
            <option value="pending_review">待核对</option>
            <option value="disputed">有争议</option>
          </select>
        </div>

        <div class="form-section">
          <label class="form-label">详述（可选）</label>
          <div class="form-row-2">
            <input v-model="personForm.courtesy_name" placeholder="字" class="input"/>
            <input v-model="personForm.art_name" placeholder="号" class="input"/>
          </div>
          <div class="form-row-3">
            <input v-model="personForm.county" placeholder="县" class="input"/>
            <input v-model="personForm.town" placeholder="镇" class="input"/>
            <input v-model="personForm.village" placeholder="村" class="input"/>
          </div>
          <textarea v-model="personForm.biography" placeholder="简介" class="input" rows="4" style="min-height:100px"></textarea>
        </div>

        <div v-if="editingPerson?.id && editingChildren.length" class="form-section">
          <label class="form-label">子女（{{ editingChildren.length }}）</label>
          <ul class="inline-links">
            <li v-for="c in editingChildren" :key="c.id">
              <a href="#" @click.prevent="editPerson(c);">{{ c.name }}</a>
            </li>
          </ul>
        </div>

        <div class="modal-actions modal-actions-spread">
          <span v-if="saveSuccessHint" class="form-success-hint">{{ saveSuccessHint }}</span>
          <button v-if="editingPerson?.id" class="btn-danger-outline" @click="deletePersonFromModal">删除成员</button>
          <div class="modal-actions-right">
            <button class="btn-secondary" @click="showPersonModal = false">取消</button>
            <button class="btn-primary" @click="savePerson">保存</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 扫描结果校正 -->
    <div v-if="parsedEditIndex !== null" class="modal">
      <div class="modal-content">
        <h3>校正成员</h3>
        <input v-model="parsedEditForm.name" placeholder="姓名" class="input"/>
        <select v-model="parsedEditForm.gender" class="input">
          <option value="unknown">未知</option>
          <option value="male">男</option>
          <option value="female">女</option>
        </select>
        <input v-model.number="parsedEditForm.birth_year" placeholder="出生年" class="input" type="number"/>
        <input v-model.number="parsedEditForm.death_year" placeholder="去世年" class="input" type="number"/>
        <input v-model.number="parsedEditForm.generation" placeholder="世代" class="input" type="number"/>
        <input v-model="parsedEditForm.generation_name" placeholder="字辈" class="input"/>
        <div class="modal-actions">
          <button class="btn-secondary" @click="parsedEditIndex = null">取消</button>
          <button class="btn-primary" @click="saveParsedEdit">保存</button>
        </div>
      </div>
    </div>

    <!-- 成员详情 -->
    <div v-if="personDetail" class="modal">
      <div class="modal-content modal-lg">
        <div class="ai-settings-header">
          <h3>{{ personDetail.person.name }}</h3>
          <button class="btn-close" @click="personDetail = null">×</button>
        </div>
        <p v-if="personDetail.person.courtesy_name">字：{{ personDetail.person.courtesy_name }}</p>
        <p v-if="personDetail.person.art_name">号：{{ personDetail.person.art_name }}</p>
        <p v-if="personDetail.person.location_text">籍贯：{{ personDetail.person.location_text }}</p>
        <p>
          第{{ personDetail.person.generation || '?' }}代
          <span v-if="personDetail.person.birth_year"> 路 {{ personDetail.person.birth_year }}<span v-if="personDetail.person.death_year">-{{ personDetail.person.death_year }}</span></span>
        </p>
        <p v-if="personDetail.person.biography">{{ personDetail.person.biography }}</p>
        <h4>家族关系</h4>
        <p v-if="personDetail.parents.length">
          父母：
          <a v-for="(p, i) in personDetail.parents" :key="p.id" href="#" class="link-person" @click.prevent="openPersonFromDetail(p)">
            {{ p.name }}<span v-if="i < personDetail.parents.length - 1">、</span>
          </a>
        </p>
        <p v-else class="sub-line">父母：未设置</p>
        <p v-if="personDetail.spouse">
          配偶：<a href="#" class="link-person" @click.prevent="openPersonFromDetail(personDetail.spouse)">{{ personDetail.spouse.name }}</a>
        </p>
        <p v-if="personDetail.children.length">
          子女：
          <a v-for="(p, i) in personDetail.children" :key="p.id" href="#" class="link-person" @click.prevent="openPersonFromDetail(p)">
            {{ p.name }}<span v-if="i < personDetail.children.length - 1">、</span>
          </a>
        </p>
        <div class="detail-actions">
          <button class="btn-xs" @click="addChild(personDetail.person); personDetail = null">+ 添加子女</button>
          <button class="btn-xs" @click="editPerson(personDetail.person); personDetail = null">编辑资料</button>
        </div>
        <div class="modal-actions">
          <button class="btn-secondary" @click="personDetail = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 删除族谱确认 -->
    <SourceCompareDialog
      v-if="showSourceCompare"
      :compare="sourceCompareData"
      :mode="sourceCompareMode"
      :relations-to-add="rebuildRelationsToAdd"
      :person-details-to-add="rebuildPersonDetailsToAdd"
      :persons-to-add="parseImportPersonsToAdd"
      @close="closeSourceCompare"
      @apply="applyFromSourceCompare"
      @open-source="openSourceFromCompare"
    />

    <AiOrganizeDialog
      v-if="showAiOrganize && currentFamily"
      :family-id="currentFamily.id"
      :source-text="activeSourceText"
      :source-version-id="currentSourceVersionId || undefined"
      :source-version-label="currentSourceVersion?.label || ''"
      :initial-prompt="aiOrganizeInitialPrompt"
      :bootstrap-from-source="aiOrganizeBootstrap"
      v-model:clean-slate="organizeCleanSlate"
      @close="closeAiOrganize"
      @plan-update="onAiPlanUpdate"
    />

    <div v-if="deleteFamilyModal" class="modal">
      <div class="modal-content">
        <h3>删除族谱</h3>
        <p class="hint" style="margin-bottom:12px">
          此操作不可撤销，将删除「{{ deleteFamilyTarget?.name }}」及全部成员与关系。
          请在下方输入族谱名称以确认：
        </p>
        <input
          v-model="deleteFamilyConfirmInput"
          class="input"
          :placeholder="deleteFamilyTarget?.name || '族谱名称'"
        />
        <div class="modal-actions">
          <button class="btn-secondary" @click="deleteFamilyModal = false">取消</button>
          <button class="btn-danger" @click="confirmDeleteFamily">确认删除</button>
        </div>
      </div>
    </div>

    <div class="toast-host" aria-live="polite">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast-item"
        :class="t.type"
      >{{ t.message }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useToast } from './composables/useToast'
import { buildPersonTree, flattenNavTree, collectAllNavIds } from './utils/treeNav'
import GenealogyReferenceViewport from './components/view/GenealogyReferenceViewport.vue'
import GenealogyReferenceView, { type ReferenceViewMode } from './components/view/GenealogyReferenceView.vue'
import OcrTextWorkspace from './components/OcrTextWorkspace.vue'
import AiOrganizeDialog from './components/AiOrganizeDialog.vue'
import FamilyChatShell from './components/FamilyChatShell.vue'
import GenealogyOrganizePanel from './components/GenealogyOrganizePanel.vue'
import SourceCompareDialog, { type SourceCompareData } from './components/SourceCompareDialog.vue'
import { type OrganizePlan, type OrganizeDiff, planHasChanges, pickDefaultApplyMode } from './types/organize'
import { type NameAnnotation, NAME_DRAG_MIME } from './utils/ocrAnnotations'

const API = '/api'
const { toasts, show: showToast } = useToast()

const workspaceLayout = ref<'chat' | 'classic'>('chat')
const families = ref<any[]>([])
const currentFamily = ref<any>(null)
const persons = ref<any[]>([])
const relations = ref<any[]>([])
const loading = ref(false)
const tab = ref('tree')
const selectedPersonId = ref<string | null>(null)
const expandedNavIds = ref<Set<string>>(new Set())
const treeZoom = ref(100)
const treePan = ref({ x: 0, y: 0 })
const treeBounds = ref({ width: 880, height: 640 })
const treeViewport = ref<HTMLElement | null>(null)
const relationLinkFromId = ref<string | null>(null)
const relationLinkMode = ref(false)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const touchCanvas = ref({
  mode: 'none' as 'none' | 'pan' | 'pinch',
  startX: 0,
  startY: 0,
  panX: 0,
  panY: 0,
  pinchDist: 0,
  pinchZoom: 100,
})
const showSearchDrawer = ref(false)
const showExportDrawer = ref(false)
const showRelationsDrawer = ref(false)
const showOrganizeDrawer = ref(false)
const showTextImportDrawer = ref(false)
const detailMobileOpen = ref(false)
const showMobileToolbarMenu = ref(false)
const mobileNavOpen = ref(false)
const personFormErrors = ref<Record<string, string>>({})
const saveSuccessHint = ref('')
const deleteFamilyModal = ref(false)
const deleteFamilyTarget = ref<{ id: string; name: string } | null>(null)
const deleteFamilyConfirmInput = ref('')
const showCreateModal = ref(false)
const showFamilyModal = ref(false)
const showPersonModal = ref(false)
const familyForm = ref({
  name: '',
  surname: '',
  description: '',
  start_generation: 1 as number,
  root_person_id: '' as string,
})
const personFilter = ref('')
const showOCR = ref(false)
const showSettings = ref(false)
const editingPerson = ref<any>(null)
const importFile = ref<HTMLInputElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

// AI 閰嶇疆
const providers = ref<any[]>([])
const keyTab = ref('minimax')
const providerKeys = ref<Record<string, { api_key: string; api_base: string; group_id?: string; configured?: boolean }>>({})
const ocrConfig = ref({ provider: 'minimax', model: 'MiniMax-M2.7' })
const parseConfig = ref({ provider: 'minimax', model: 'MiniMax-M2.7' })

type TestState = { loading: boolean; ok: boolean | null; message: string; preview: string; latency: number }
const emptyTest = (): TestState => ({ loading: false, ok: null, message: '', preview: '', latency: 0 })
const testStatus = ref<Record<'key' | 'ocr' | 'parse', TestState>>({
  key: emptyTest(),
  ocr: emptyTest(),
  parse: emptyTest(),
})

const visionProviders = computed(() =>
  providers.value.filter(p => p.supports_vision && (p.vision_models?.length || p.vision_model))
)

const ocrModelOptions = computed(() => {
  const p = providers.value.find(item => item.id === ocrConfig.value.provider)
  if (!p) return []
  const list = p.vision_models?.length ? p.vision_models : (p.vision_model ? [p.vision_model] : [])
  if (ocrConfig.value.model && !list.includes(ocrConfig.value.model)) {
    return [ocrConfig.value.model, ...list]
  }
  return list
})

const parseModelOptions = computed(() => {
  const p = providers.value.find(item => item.id === parseConfig.value.provider)
  if (!p) return []
  const list = p.text_models?.length ? p.text_models : (p.text_model ? [p.text_model] : [])
  if (parseConfig.value.model && !list.includes(parseConfig.value.model)) {
    return [parseConfig.value.model, ...list]
  }
  return list
})


const activeProvider = computed(() =>
  providers.value.find(p => p.id === keyTab.value) || { id: 'minimax', label: 'MiniMax' }
)

function providerLabel(p: { id?: string; label?: string; name?: string }) {
  return p.label || p.name || p.id || ''
}

function getProvider(id: string) {
  return providers.value.find(p => p.id === id) || { id, label: id }
}

function initProviderKeys(list: any[]) {
  const keys: Record<string, { api_key: string; api_base: string; group_id?: string; configured?: boolean }> = {}
  for (const p of list) {
    keys[p.id] = providerKeys.value[p.id] || {
      api_key: '',
      api_base: p.id === 'custom' ? '' : (p.api_base || ''),
      group_id: '',
      configured: false,
    }
  }
  providerKeys.value = keys
}

async function fetchProviders() {
  try {
    const res = await api('GET', '/ai/providers')
    providers.value = res
    initProviderKeys(res)
  } catch {
    providers.value = [
      { id: 'minimax', name: 'MiniMax', label: 'MiniMax', vision_model: 'MiniMax-M2.7', text_model: 'MiniMax-M2.7', vision_models: ['MiniMax-M2.7', 'MiniMax-Text-01', 'MiniMax-Image-01'], text_models: ['MiniMax-M2.7', 'abab6.5s-chat', 'MiniMax-Text-01'], is_free: false, supports_vision: true },
      { id: 'siliconflow', name: 'SiliconFlow', label: '硅基流动', vision_model: 'Qwen/Qwen2-VL-72B-Instruct', text_model: 'Qwen/Qwen2.5-72B-Instruct', vision_models: ['Qwen/Qwen2-VL-72B-Instruct'], text_models: ['Qwen/Qwen2.5-72B-Instruct', 'deepseek-ai/DeepSeek-V3'], is_free: true, supports_vision: true },
      { id: 'qwen', name: 'Qwen', label: '通义千问', vision_model: 'qwen-vl-plus', text_model: 'qwen-plus', vision_models: ['qwen-vl-plus', 'qwen-vl-max'], text_models: ['qwen-plus', 'qwen-turbo', 'qwen-max'], is_free: false, supports_vision: true },
      { id: 'openai', name: 'OpenAI', label: 'OpenAI', vision_model: 'gpt-4o', text_model: 'gpt-4o', vision_models: ['gpt-4o', 'gpt-4o-mini'], text_models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'], is_free: false, supports_vision: true },
      { id: 'deepseek', name: 'DeepSeek', label: 'DeepSeek', vision_model: '', text_model: 'deepseek-chat', vision_models: [], text_models: ['deepseek-chat', 'deepseek-coder'], is_free: true, supports_vision: false },
      { id: 'zhipu', name: 'GLM', label: '智谱 GLM', vision_model: 'glm-4v-9b', text_model: 'glm-4-plus', vision_models: ['glm-4v-9b', 'glm-4v-plus'], text_models: ['glm-4-plus', 'glm-4-flash'], is_free: false, supports_vision: true },
      { id: 'custom', name: 'Custom', label: '自定义', vision_model: '', text_model: '', vision_models: [], text_models: [], is_free: false, supports_vision: true },
    ]
    initProviderKeys(providers.value)
  }
}

function onOcrProviderChange() {
  const p = providers.value.find(item => item.id === ocrConfig.value.provider)
  const models = p?.vision_models?.length ? p.vision_models : (p?.vision_model ? [p.vision_model] : [])
  if (models.length) ocrConfig.value.model = models[0]
}

function onParseProviderChange() {
  const p = providers.value.find(item => item.id === parseConfig.value.provider)
  const models = p?.text_models?.length ? p.text_models : (p?.text_model ? [p.text_model] : [])
  if (models.length) parseConfig.value.model = models[0]
}

// OCR 鐩稿叧
const ocrStep = ref('')
const previewImage = ref('')
const ocrResult = ref<any>({ text: '' })
const parsedPersons = ref<any[]>([])
const ocrLoading = ref(false)
const ocrFamilyId = ref('')
const scanValidation = ref<any>(null)
const ocrEditableText = ref('')
const ocrAnnotations = ref<NameAnnotation[]>([])
const ocrReparsing = ref(false)
const ocrRelationDescription = ref('')
const ocrCustomText = ref('')
const ocrVersionTab = ref<'v1' | 'v2' | 'v3'>('v1')
const sourceVersionDiff = ref<any>(null)
const ocrRegeneratingV2 = ref(false)
const ocrDescribingV2 = ref(false)
const ocrParseSteps = ref<string[]>([])
const ocrParsedBaseline = ref('')
const parsedListDragOver = ref(false)
const treeNameDropActive = ref(false)
const relationLinkFromName = ref<string | null>(null)
const pendingTextRelations = ref<any[]>([])
const familySourceDirty = ref(false)
const sourceVersions = ref<any[]>([])
const currentSourceVersionId = ref<string | null>(null)
const lastSourceVersionId = ref<string | null>(null)

const newFamily = ref({ name: '', surname: '', description: '' })
const personForm = ref({
  name: '', gender: 'unknown', birth_year: null as number | null,
  death_year: null as number | null, generation: null as number | null,
  generation_name: '', generation_prefix: '', parent_id: '',
  courtesy_name: '', art_name: '', county: '', town: '', village: '',
  biography: '', spouse_id: '',
})

const genealogyViewMode = ref<ReferenceViewMode>('page')
const referenceViewportRef = ref<InstanceType<typeof GenealogyReferenceViewport> | null>(null)
const referenceZoomLabel = ref('100%')
const treeStyle = ref<'silkworm'>('silkworm')
const treeNodes = ref<any[]>([])
const searchQuery = ref('')
const searchMode = ref<'keyword' | 'nl'>('keyword')
const searchResults = ref<any[]>([])
const searchLoading = ref(false)
const parsedRelations = ref<any[]>([])
const personDetail = ref<any>(null)
const parsedEditIndex = ref<number | null>(null)
const parsedEditForm = ref<any>({})
const newRelation = ref({
  from_person_id: '',
  to_person_id: '',
  relation_type: 'parent_child',
  status: 'confirmed',
})
const genealogyStats = ref<any>(null)
const treePreviewNodes = ref<any[]>([])
const buildStats = ref<any>(null)
const buildLoading = ref(false)
const showAiOrganize = ref(false)
const aiOrganizeInitialPrompt = ref('')
const aiOrganizeBootstrap = ref(false)
const pendingOrganizePlan = ref<OrganizePlan | null>(null)
const pendingOrganizeDiff = ref<OrganizeDiff | null>(null)
const organizeApplyMode = ref<'merge' | 'replace'>('merge')
const organizeCleanSlate = ref(false)
let organizePlanEditTimer: ReturnType<typeof setTimeout> | null = null
const textParseFailedHint = ref('')
const showSourceCompare = ref(false)
const sourceCompareMode = ref<'source' | 'parse'>('source')
const sourceCompareData = ref<SourceCompareData | null>(null)
const rebuildRelationsToAdd = ref(0)
const rebuildPersonDetailsToAdd = ref(0)
const syncPersonDetailsLoading = ref(false)
const parseImportPersonsToAdd = ref(0)
const pendingParseImport = ref<{ familyId: string; persons: any[]; relations: any[] } | null>(null)

const isAbsoluteTreeLayout = computed(() =>
  treeStyle.value === 'silkworm' || treeStyle.value === 'radial',
)

/** 垂丝图左侧「第N世」标签列宽度 */
const SILKWORM_LABEL_COL = 88

const treeDisplayWidth = computed(() => {
  const base = treeBounds.value.width || 880
  return treeStyle.value === 'silkworm' ? base + SILKWORM_LABEL_COL : base
})

const silkwormGenerationRows = computed(() => {
  if (treeStyle.value !== 'silkworm' || !treeNodes.value.length) return []
  const byGen = new Map<number, any[]>()
  for (const n of treeNodes.value) {
    const g = Number(n.generation) || 1
    if (!byGen.has(g)) byGen.set(g, [])
    byGen.get(g)!.push(n)
  }
  const rows: { generation: number; top: number; height: number; count: number; even: boolean }[] = []
  let idx = 0
  for (const g of [...byGen.keys()].sort((a, b) => a - b)) {
    const nodes = byGen.get(g)!
    const first = nodes.reduce((a, b) =>
      ((a.layout?.offset_y ?? 0) < (b.layout?.offset_y ?? 0) ? a : b),
    )
    const rowY = first.layout?.offset_y ?? 0
    const rowH = Math.max(
      first.layout?.node_height || 72,
      ...nodes.map((n) => n.layout?.node_height || 72),
    )
    rows.push({ generation: g, top: rowY, height: rowH + 16, count: nodes.length, even: idx % 2 === 0 })
    idx += 1
  }
  return rows
})

const navTree = computed(() => buildPersonTree(persons.value))
const flatNavItems = computed(() => flattenNavTree(navTree.value, expandedNavIds.value))

const selectedPerson = computed(() =>
  persons.value.find((p) => p.id === selectedPersonId.value) || null,
)

const displayPerson = computed(() => personDetail.value?.person || selectedPerson.value)

const selectedPersonSourceExcerpt = computed(() => {
  const fromApi = personDetail.value?.source_excerpt
  if (fromApi) return fromApi
  const name = displayPerson.value?.name
  if (!name || !activeSourceText.value) return ''
  const lines = activeSourceText.value.split('\n')
  const hits = lines.filter((ln) => ln.includes(name)).slice(0, 5)
  return hits.join('\n')
})

const selectedPersonRelations = computed(() => {
  const pid = selectedPersonId.value
  if (!pid) return []
  const out: {
    id: string
    label: string
    typeLabel: string
    otherId: string
    relationType: string
  }[] = []
  for (const r of relations.value) {
    if (r.from_person_id === pid) {
      out.push({
        id: r.id,
        otherId: r.to_person_id,
        label: `→ ${r.to_name || '?'}`,
        typeLabel: relationTypeLabel(r.relation_type, r.relation_subtype),
        relationType: r.relation_type,
      })
    }
    if (r.to_person_id === pid) {
      out.push({
        id: r.id,
        otherId: r.from_person_id,
        label: `← ${r.from_name || '?'}`,
        typeLabel: relationTypeLabel(r.relation_type, r.relation_subtype),
        relationType: r.relation_type,
      })
    }
  }
  return out
})

const treeCompact = computed(() => maxGeneration.value >= 15 || treeNodes.value.length > 60)

const treeNodeById = computed(() => {
  const map = new Map<string, any>()
  for (const n of treeNodes.value) map.set(n.id, n)
  return map
})

const treeEdges = computed(() => {
  if (!isAbsoluteTreeLayout.value) return []
  const labelOffset = treeStyle.value === 'silkworm' ? SILKWORM_LABEL_COL : 0
  const edges: { x1: number; y1: number; x2: number; y2: number; type: string }[] = []
  for (const r of relations.value) {
    if (r.relation_type !== 'parent_child' && r.relation_type !== 'spouse') continue
    const from = treeNodeById.value.get(r.from_person_id)
    const to = treeNodeById.value.get(r.to_person_id)
    if (!from?.layout || !to?.layout) continue
    const fw = from.layout.node_width || 128
    const fh = from.layout.node_height || 56
    const tw = to.layout.node_width || 128
    edges.push({
      x1: labelOffset + from.layout.offset_x + fw / 2,
      y1: from.layout.offset_y + fh,
      x2: labelOffset + to.layout.offset_x + tw / 2,
      y2: to.layout.offset_y,
      type: r.relation_type,
    })
  }
  return edges
})

const maxGeneration = computed(() => {
  if (!persons.value.length) return 0
  return Math.max(...persons.value.map(p => p.generation || 0))
})

const ocrTextDirty = computed(() =>
  ocrStep.value === 'result'
  && ocrEditableText.value !== ocrParsedBaseline.value,
)

const currentSourceVersion = computed(() =>
  sourceVersions.value.find((v) => v.id === currentSourceVersionId.value) || null,
)

const sourceVersionBadge = computed(() => {
  if (sourceVersions.value.length && currentSourceVersion.value) {
    const v = currentSourceVersion.value
    return ` v${v.version_no}${v.status === 'confirmed' ? '✓' : ''}`
  }
  return currentFamily.value?.source_text ? ' ✓' : ''
})

const activeSourceText = computed(() => {
  const fromEditor = ocrEditableText.value.trim()
  if (fromEditor) return fromEditor
  const fromVersion = currentSourceVersion.value?.source_text?.trim()
  if (fromVersion) return fromVersion
  return (currentFamily.value?.source_text || '').trim()
})

const digitizeSourceText = computed(() => {
  const v3 = ocrCustomText.value.trim()
  if (v3) return v3
  const v2 = ocrRelationDescription.value.trim()
  if (v2) return v2
  return ocrEditableText.value.trim()
})

function familyInitial(f: { name?: string; surname?: string }) {
  const s = (f.surname || f.name || '族').trim()
  return s.charAt(0)
}

const filteredPersons = computed(() => {
  const q = personFilter.value.trim()
  if (!q) return persons.value
  return persons.value.filter(p => (p.name || '').includes(q))
})

const parentCandidates = computed(() => {
  const selfId = editingPerson.value?.id
  const gen = personForm.value.generation
  return persons.value.filter(p => {
    if (p.id === selfId) return false
    if (gen && p.generation && p.generation >= gen) return false
    return true
  })
})

const spouseCandidates = computed(() => {
  const selfId = editingPerson.value?.id
  return persons.value.filter(p => p.id !== selfId)
})

const editingChildren = computed(() => {
  if (!editingPerson.value?.id) return []
  return persons.value.filter(p => p.parent_id === editingPerson.value.id)
})

function genderLabel(g: string) {
  if (g === 'male') return '男'
  if (g === 'female') return '女'
  return ''
}

function parentName(parentId: string) {
  if (!parentId) return ''
  return persons.value.find(p => p.id === parentId)?.name || ''
}

function spouseName(spouseId: string) {
  if (!spouseId) return ''
  return persons.value.find(p => p.id === spouseId)?.name || ''
}

function relationTypeLabel(t: string, subtype?: string) {
  let base = t || '关系'
  if (t === 'spouse') base = '配偶'
  else if (t === 'parent_child') base = '父子'
  if (subtype === 'adopted') return `${base} · 过继`
  if (subtype === 'dual_inheritance') return `${base} · 兼祧`
  if (subtype === 'step') return `${base} · 继配`
  return base
}

// ==================== API 请求 ====================

const API_TIMEOUT = 15000
const API_TIMEOUT_LONG = 300000 // OCR / 两阶段解析 / AI 整理

async function api(method: string, path: string, data?: any, timeoutMs = API_TIMEOUT) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${API}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
      signal: controller.signal,
    })
    const text = await res.text()
    try {
      const json = JSON.parse(text)
      if (!res.ok && !json.message && !json.error) {
        json.success = false
        json.message = `HTTP ${res.status}`
      }
      return json
    } catch {
      return { success: false, message: res.ok ? '响应解析失败' : `HTTP ${res.status}: ${text.slice(0, 120)}` }
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      return { success: false, message: '请求超时，请确认后端已启动（backend 目录运行 python main.py）' }
    }
    return { success: false, message: '无法连接后端，请确认 backend 已启动' }
  } finally {
    clearTimeout(timer)
  }
}

const TEST_MIN_DISPLAY_MS = 2000

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// ==================== 鏃忚氨鎿嶄綔 ====================

async function fetchFamilies() {
  loading.value = true
  try {
    const res = await api('GET', '/families')
    if (Array.isArray(res)) {
      families.value = res
    } else {
      families.value = []
      showToast(res.message || '加载族谱失败', 'error')
    }
  } finally {
    loading.value = false
  }
}

async function createFamily() {
  if (!newFamily.value.name) return
  const res = await api('POST', '/families', newFamily.value)
  if (res.success) {
    newFamily.value = { name: '', surname: '', description: '' }
    showCreateModal.value = false
    fetchFamilies()
  }
}

function requestDeleteFamily(f: { id: string; name: string }) {
  deleteFamilyTarget.value = f
  deleteFamilyConfirmInput.value = ''
  deleteFamilyModal.value = true
}

async function confirmDeleteFamily() {
  const target = deleteFamilyTarget.value
  if (!target) return
  if (deleteFamilyConfirmInput.value.trim() !== (target.name || '').trim()) {
    showToast('请输入正确的族谱名称以确认删除', 'error')
    return
  }
  const res = await api('DELETE', `/families/${target.id}`)
  if (res.success === false) {
    showToast(res.message || res.detail || '删除失败', 'error')
    return
  }
  deleteFamilyModal.value = false
  deleteFamilyTarget.value = null
  if (currentFamily.value?.id === target.id) leaveFamily()
  showToast('族谱已删除', 'success')
  fetchFamilies()
}

async function deleteFamily(id: string) {
  const f = families.value.find((x) => x.id === id)
  if (f) requestDeleteFamily(f)
  else requestDeleteFamily({ id, name: '' })
}

function expandAllNav() {
  expandedNavIds.value = new Set(collectAllNavIds(navTree.value))
}

function leaveFamily() {
  currentFamily.value = null
  selectedPersonId.value = null
  showSearchDrawer.value = false
  showExportDrawer.value = false
  showRelationsDrawer.value = false
  showMobileToolbarMenu.value = false
  mobileNavOpen.value = false
  detailMobileOpen.value = false
}

function leaveFamilyFromChat() {
  leaveFamily()
  workspaceLayout.value = 'chat'
}

function enterClassicWorkspace(panel?: string) {
  workspaceLayout.value = 'classic'
  if (panel === 'organize' || panel === 'diff') {
    showOrganizeDrawer.value = true
  }
  nextTick(() => fitTreeToView())
}

async function onChatShellRefresh() {
  await fetchFamilies()
  if (currentFamily.value?.id) {
    await fetchPersons()
    await fetchRelations()
  }
}

function isMobileViewport() {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 640px)').matches
}

function closeDetailMobile() {
  detailMobileOpen.value = false
}

function selectPerson(id: string, opts?: { focusOnTree?: boolean }) {
  selectedPersonId.value = id
  detailMobileOpen.value = true
  personDetail.value = null
  const p = persons.value.find((x) => x.id === id)
  if (p) void viewPersonDetail(p)
  if (opts?.focusOnTree && treeNodeById.value.has(id)) {
    nextTick(() => focusPerson(id))
  }
}

function selectPersonFromNav(id: string) {
  selectPerson(id)
}

function selectPersonFromReference(id: string) {
  selectPerson(id)
}

function syncReferenceZoomLabel() {
  const s = referenceViewportRef.value?.scale?.value ?? 1
  referenceZoomLabel.value = `${Math.round(s * 100)}%`
}

function referenceZoomIn() {
  referenceViewportRef.value?.zoomIn()
  syncReferenceZoomLabel()
}

function referenceZoomOut() {
  referenceViewportRef.value?.zoomOut()
  syncReferenceZoomLabel()
}

function referenceZoomReset() {
  referenceViewportRef.value?.zoomReset()
  syncReferenceZoomLabel()
}

function referenceFitView() {
  referenceViewportRef.value?.fitView()
  syncReferenceZoomLabel()
}

function focusPerson(id: string) {
  selectPerson(id)
  const node = treeNodeById.value.get(id)
  if (node?.layout && treeViewport.value) {
    const rect = treeViewport.value.getBoundingClientRect()
    const lw = node.layout.node_width || 128
    const lh = node.layout.node_height || 56
    zoomAtPoint(rect.left + rect.width / 2, rect.top + rect.height / 2, Math.min(200, treeZoom.value + 20))
    treePan.value = {
      x: rect.width / 2 - (node.layout.offset_x + lw / 2) * (treeZoom.value / 100),
      y: rect.height / 2 - (node.layout.offset_y + lh / 2) * (treeZoom.value / 100),
    }
  } else {
    treeZoom.value = Math.min(200, treeZoom.value + 25)
  }
}

const MIN_TREE_ZOOM = 5
const MAX_TREE_ZOOM = 250

function clampTreeZoom(v: number) {
  return Math.min(MAX_TREE_ZOOM, Math.max(MIN_TREE_ZOOM, v))
}

function zoomAtPoint(clientX: number, clientY: number, nextZoom: number) {
  const vp = treeViewport.value
  const z = clampTreeZoom(nextZoom)
  if (!vp) {
    treeZoom.value = z
    return
  }
  const rect = vp.getBoundingClientRect()
  const oldScale = treeZoom.value / 100
  const newScale = z / 100
  const px = (clientX - rect.left - treePan.value.x) / oldScale
  const py = (clientY - rect.top - treePan.value.y) / oldScale
  treeZoom.value = z
  treePan.value = {
    x: clientX - rect.left - px * newScale,
    y: clientY - rect.top - py * newScale,
  }
}

function toggleNavExpand(id: string) {
  const next = new Set(expandedNavIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedNavIds.value = next
}

function zoomIn() {
  const vp = treeViewport.value
  if (!vp) {
    treeZoom.value = clampTreeZoom(treeZoom.value + 10)
    return
  }
  const rect = vp.getBoundingClientRect()
  zoomAtPoint(rect.left + rect.width / 2, rect.top + rect.height / 2, treeZoom.value + 10)
}

function zoomOut() {
  const vp = treeViewport.value
  if (!vp) {
    treeZoom.value = clampTreeZoom(treeZoom.value - 10)
    return
  }
  const rect = vp.getBoundingClientRect()
  zoomAtPoint(rect.left + rect.width / 2, rect.top + rect.height / 2, treeZoom.value - 10)
}

function zoomReset() {
  treeZoom.value = 100
  treePan.value = { x: 0, y: 0 }
  nextTick(() => fitTreeToView())
}

function fitTreeToView() {
  const vp = treeViewport.value
  if (!vp || !treeNodes.value.length) return
  const pad = 28
  const vw = Math.max(vp.clientWidth - pad * 2, 120)
  const vh = Math.max(vp.clientHeight - pad * 2, 120)
  const bw = treeDisplayWidth.value
  const bh = treeBounds.value.height || 640
  const scalePct = clampTreeZoom(Math.floor(Math.min(vw / bw, vh / bh) * 100))
  treeZoom.value = scalePct
  const sw = bw * (scalePct / 100)
  const sh = bh * (scalePct / 100)
  treePan.value = {
    x: pad + Math.max(0, (vw - sw) / 2),
    y: pad + Math.max(0, (vh - sh) / 2),
  }
}

function onTreeWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? -8 : 8
  zoomAtPoint(e.clientX, e.clientY, treeZoom.value + delta)
}

function onCanvasPanStart(e: MouseEvent) {
  if (relationLinkMode.value) return
  if ((e.target as HTMLElement).closest('.tree-node-card')) return
  isPanning.value = true
  panStart.value = { x: e.clientX, y: e.clientY, panX: treePan.value.x, panY: treePan.value.y }
  window.addEventListener('mousemove', onCanvasPanMove)
  window.addEventListener('mouseup', onCanvasPanEnd)
}

function onCanvasPanMove(e: MouseEvent) {
  if (!isPanning.value) return
  treePan.value = {
    x: panStart.value.panX + (e.clientX - panStart.value.x),
    y: panStart.value.panY + (e.clientY - panStart.value.y),
  }
}

function onCanvasPanEnd() {
  isPanning.value = false
  window.removeEventListener('mousemove', onCanvasPanMove)
  window.removeEventListener('mouseup', onCanvasPanEnd)
}

function touchPinchDistance(touches: TouchList) {
  const dx = touches[0].clientX - touches[1].clientX
  const dy = touches[0].clientY - touches[1].clientY
  return Math.hypot(dx, dy)
}

function touchMidpoint(touches: TouchList) {
  return {
    x: (touches[0].clientX + touches[1].clientX) / 2,
    y: (touches[0].clientY + touches[1].clientY) / 2,
  }
}

function resetTouchCanvas() {
  touchCanvas.value = {
    mode: 'none',
    startX: 0,
    startY: 0,
    panX: 0,
    panY: 0,
    pinchDist: 0,
    pinchZoom: treeZoom.value,
  }
  isPanning.value = false
}

function onCanvasTouchStart(e: TouchEvent) {
  if (relationLinkMode.value) return
  if ((e.target as HTMLElement).closest('.tree-node-card')) return
  if (e.touches.length === 1) {
    touchCanvas.value = {
      mode: 'pan',
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      panX: treePan.value.x,
      panY: treePan.value.y,
      pinchDist: 0,
      pinchZoom: treeZoom.value,
    }
    isPanning.value = true
  } else if (e.touches.length === 2) {
    touchCanvas.value = {
      mode: 'pinch',
      startX: 0,
      startY: 0,
      panX: treePan.value.x,
      panY: treePan.value.y,
      pinchDist: touchPinchDistance(e.touches),
      pinchZoom: treeZoom.value,
    }
    isPanning.value = false
  }
}

function onCanvasTouchMove(e: TouchEvent) {
  const ts = touchCanvas.value
  if (ts.mode === 'pan' && e.touches.length === 1) {
    e.preventDefault()
    treePan.value = {
      x: ts.panX + (e.touches[0].clientX - ts.startX),
      y: ts.panY + (e.touches[0].clientY - ts.startY),
    }
    return
  }
  if (ts.mode === 'pinch' && e.touches.length === 2 && ts.pinchDist > 0) {
    e.preventDefault()
    const dist = touchPinchDistance(e.touches)
    const mid = touchMidpoint(e.touches)
    const scale = dist / ts.pinchDist
    zoomAtPoint(mid.x, mid.y, ts.pinchZoom * scale)
  }
}

function onCanvasTouchEnd(e: TouchEvent) {
  if (e.touches.length === 0) {
    resetTouchCanvas()
    return
  }
  if (e.touches.length === 1 && touchCanvas.value.mode === 'pinch') {
    touchCanvas.value = {
      mode: 'pan',
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      panX: treePan.value.x,
      panY: treePan.value.y,
      pinchDist: 0,
      pinchZoom: treeZoom.value,
    }
    isPanning.value = true
  }
}

function openAddPerson() {
  showPersonModal.value = true
  editingPerson.value = null
  personFormErrors.value = {}
  saveSuccessHint.value = ''
  resetPersonForm()
}

function goOCRFromFamily() {
  const fid = currentFamily.value?.id
  goOCR()
  if (fid) {
    ocrFamilyId.value = fid
    ocrStep.value = 'upload'
  }
}

async function doSearchAndSelect() {
  await doSearch()
  if (searchResults.value.length) selectPerson(searchResults.value[0].id)
}

function validatePersonForm(): boolean {
  const errs: Record<string, string> = {}
  const name = (personForm.value.name || '').trim()
  if (!name) errs.name = '姓名不能为空'
  else if (name.length > 50) errs.name = '姓名长度不超过 50 个字符'
  const birth = personForm.value.birth_year
  const death = personForm.value.death_year
  const yearNow = new Date().getFullYear()
  if (birth != null && (birth < 1000 || birth > yearNow)) {
    errs.birth_year = `生年应在 1000–${yearNow} 之间`
  }
  if (death != null && birth != null && death < birth) {
    errs.death_year = '卒年不能早于生年'
  }
  personFormErrors.value = errs
  return Object.keys(errs).length === 0
}

async function backupFamilyLocal() {
  if (!currentFamily.value?.id) return
  try {
    const data = await api('GET', `/families/${currentFamily.value.id}/export`)
    const key = 'genealogy_backups'
    const raw = localStorage.getItem(key)
    const list: { ts: number; familyId: string; name: string; data: unknown }[] = raw ? JSON.parse(raw) : []
    list.unshift({
      ts: Date.now(),
      familyId: currentFamily.value.id,
      name: currentFamily.value.name || '族谱',
      data,
    })
    localStorage.setItem(key, JSON.stringify(list.slice(0, 5)))
    showToast('已备份到浏览器本地（保留最近 5 次）', 'success')
  } catch {
    showToast('备份失败', 'error')
  }
}

async function viewFamily(id: string) {
  const detail = await api('GET', `/families/${id}`)
  currentFamily.value = detail.id ? detail : { id }
  loadFamilySourceFromDetail(currentFamily.value)
  tab.value = 'tree'
  personFilter.value = ''
  treeZoom.value = 100
  treePan.value = { x: 0, y: 0 }
  relationLinkFromName.value = null
  pendingTextRelations.value = []
  await fetchPersons()
  await fetchRelations()
  expandAllNav()
  await loadTree()
  if (persons.value.length && !selectedPersonId.value) {
    selectedPersonId.value = persons.value[0].id
  }
  await fetchSourceVersions()
  await syncPersonDetailsFromSourceQuiet()
  await loadOrganizeState(id)
  if (!isMobileViewport() && (currentFamily.value.source_text || sourceVersions.value.length)) {
    showTextImportDrawer.value = true
  } else {
    showTextImportDrawer.value = false
  }
  workspaceLayout.value = 'chat'
  await nextTick()
  fitTreeToView()
}

function versionOptionLabel(v: { label?: string; version_no?: number; status?: string; version_kind?: string }) {
  const kindTag =
    v.version_kind === 'ocr_raw' ? '图' :
    v.version_kind === 'relation_desc' ? '述' :
    v.version_kind === 'custom' ? '改' : ''
  const name = v.label || `第${v.version_no}版`
  const prefix = kindTag ? `[${kindTag}] ` : ''
  const status = v.status === 'confirmed' ? '（已确认）' : '（草稿）'
  return `${prefix}${name}${status}`
}

function initCustomFromV2() {
  if (!ocrRelationDescription.value.trim()) {
    showToast('版本二暂无内容', 'info')
    return
  }
  ocrCustomText.value = ocrRelationDescription.value
  ocrVersionTab.value = 'v3'
  showToast('已从版本二复制到修正稿', 'success')
}

async function regenerateOcrV2() {
  if (!ocrEditableText.value.trim()) return
  ocrRegeneratingV2.value = true
  try {
    const res = await api('POST', `/families/${ocrFamilyId.value}/source-versions/regenerate-relation-desc`, {
      ocr_text: ocrEditableText.value,
      parse: parseConfig.value,
    }, API_TIMEOUT_LONG)
    if (!res.success) {
      showToast(res.detail || res.message || '生成失败', 'error')
      return
    }
    ocrRelationDescription.value = res.relation_description || ''
    ocrVersionTab.value = 'v2'
    showToast('版本二关系描述已重新生成', 'success')
  } catch (e: any) {
    showToast(e.message || '生成失败', 'error')
  } finally {
    ocrRegeneratingV2.value = false
  }
}

async function compareSourceVersions() {
  const fid = currentFamily.value?.id
  if (!fid || sourceVersions.value.length < 2) return
  const v2 = sourceVersions.value.find((v) => v.version_kind === 'relation_desc')
  const v3 = sourceVersions.value.find((v) => v.version_kind === 'custom')
  const fromId = v2?.id || sourceVersions.value[0]?.id
  const toId = v3?.id || sourceVersions.value[sourceVersions.value.length - 1]?.id
  if (!fromId || !toId || fromId === toId) {
    showToast('需要至少两个不同版本才能对比', 'info')
    return
  }
  const res = await api('GET', `/families/${fid}/source-versions/compare?from_id=${fromId}&to_id=${toId}`)
  if (!res.success) {
    showToast(res.detail || '对比失败', 'error')
    return
  }
  sourceVersionDiff.value = res.diff
  showToast(res.diff?.summary || '对比完成', 'info')
}

function applySourceVersionToEditor(version: any) {
  const text = version?.source_text || ''
  const kind = version?.version_kind
  if (kind === 'relation_desc') {
    ocrRelationDescription.value = text
  } else if (kind === 'custom') {
    ocrCustomText.value = text
  } else {
    ocrEditableText.value = text
    ocrParsedBaseline.value = text
    try {
      const raw = version?.source_annotations
      if (!raw) ocrAnnotations.value = []
      else if (typeof raw === 'string') ocrAnnotations.value = JSON.parse(raw)
      else ocrAnnotations.value = raw
    } catch {
      ocrAnnotations.value = []
    }
  }
  familySourceDirty.value = false
}

async function fetchSourceVersions() {
  const fid = currentFamily.value?.id
  if (!fid) {
    sourceVersions.value = []
    currentSourceVersionId.value = null
    return
  }
  try {
    const res = await api('GET', `/families/${fid}/source-versions`)
    sourceVersions.value = res.versions || []
    const activeId = res.active_version_id || sourceVersions.value[sourceVersions.value.length - 1]?.id || null
    if (activeId && (!currentSourceVersionId.value || !sourceVersions.value.some((v) => v.id === currentSourceVersionId.value))) {
      currentSourceVersionId.value = activeId
    }
    lastSourceVersionId.value = currentSourceVersionId.value
    const current = sourceVersions.value.find((v) => v.id === currentSourceVersionId.value)
    if (current) {
      applySourceVersionToEditor(current)
    }
  } catch {
    sourceVersions.value = []
  }
}

function onSourceVersionSelect() {
  const nextId = currentSourceVersionId.value
  const next = sourceVersions.value.find((v) => v.id === nextId)
  if (!next) return
  if (ocrEditableText.value !== ocrParsedBaseline.value && !confirm('当前版本有未保存修改，切换将丢失。继续？')) {
    currentSourceVersionId.value = lastSourceVersionId.value
    return
  }
  applySourceVersionToEditor(next)
  lastSourceVersionId.value = nextId
}

async function saveAsNewSourceVersion() {
  const fid = currentFamily.value?.id
  if (!fid || !ocrEditableText.value.trim()) return
  const nextNo = (sourceVersions.value[sourceVersions.value.length - 1]?.version_no || 0) + 1
  const defaultLabel = `第${nextNo}版`
  const inputLabel = prompt('另存为新版本，请输入版本名称：', defaultLabel)
  if (inputLabel === null) return
  const label = inputLabel.trim() || defaultLabel
  const res = await api('POST', `/families/${fid}/source-versions`, {
    source_text: ocrEditableText.value,
    source_annotations: ocrAnnotations.value,
    label,
    status: 'draft',
    set_active: true,
  })
  if (!res.success) {
    showToast(res.detail || res.message || '另存为失败', 'error')
    return
  }
  sourceVersions.value = [...sourceVersions.value, res.version]
  currentSourceVersionId.value = res.version.id
  lastSourceVersionId.value = res.version.id
  ocrParsedBaseline.value = ocrEditableText.value
  familySourceDirty.value = false
  textParseFailedHint.value = ''
  if (res.family) currentFamily.value = { ...currentFamily.value, ...res.family }
  showToast(`已另存为「${res.version.label || label}」（草稿）`, 'success')
}

async function deleteCurrentSourceVersion() {
  const fid = currentFamily.value?.id
  const vid = currentSourceVersionId.value
  if (!fid || !vid) return
  if (sourceVersions.value.length <= 1) {
    showToast('至少需保留一个原文版本', 'error')
    return
  }
  const v = currentSourceVersion.value
  const name = v?.label || `第${v?.version_no}版`
  const ok = confirm(`确定删除原文版本「${name}」？\n\n删除后不可恢复。`)
  if (!ok) return
  const res = await api('DELETE', `/families/${fid}/source-versions/${vid}`)
  if (!res.success) {
    showToast(res.detail || res.message || '删除失败', 'error')
    return
  }
  sourceVersions.value = res.versions || []
  currentSourceVersionId.value = res.active_version_id || sourceVersions.value[sourceVersions.value.length - 1]?.id || null
  lastSourceVersionId.value = currentSourceVersionId.value
  const current = sourceVersions.value.find((item) => item.id === currentSourceVersionId.value)
  if (current) applySourceVersionToEditor(current)
  if (res.family) currentFamily.value = { ...currentFamily.value, ...res.family }
  textParseFailedHint.value = ''
  showToast(`已删除「${name}」`, 'success')
}

async function confirmCurrentSourceVersion() {
  const fid = currentFamily.value?.id
  const vid = currentSourceVersionId.value
  if (!fid || !vid) return
  if (familySourceDirty.value) await saveFamilySourceText()
  const res = await api('POST', `/families/${fid}/source-versions/${vid}/confirm`)
  if (!res.success) {
    showToast(res.detail || res.message || '确认失败', 'error')
    return
  }
  const idx = sourceVersions.value.findIndex((v) => v.id === vid)
  if (idx >= 0) sourceVersions.value[idx] = res.version
  if (res.family) currentFamily.value = { ...currentFamily.value, ...res.family }
  showToast('此版已确认，AI 整理将使用此版本原文', 'success')
}

function loadFamilySourceFromDetail(family: any) {
  ocrEditableText.value = family?.source_text || ''
  ocrParsedBaseline.value = family?.source_text || ''
  try {
    const raw = family?.source_annotations
    if (!raw) {
      ocrAnnotations.value = []
    } else if (typeof raw === 'string') {
      ocrAnnotations.value = JSON.parse(raw)
    } else {
      ocrAnnotations.value = raw
    }
  } catch {
    ocrAnnotations.value = []
  }
}

async function saveFamilySourceText() {
  const fid = currentFamily.value?.id
  if (!fid) return
  let res
  if (currentSourceVersionId.value) {
    res = await api('PUT', `/families/${fid}/source-versions/${currentSourceVersionId.value}`, {
      source_text: ocrEditableText.value,
      source_annotations: ocrAnnotations.value,
    })
  } else {
    res = await api('PUT', `/families/${fid}/source-text`, {
      source_text: ocrEditableText.value,
      source_annotations: ocrAnnotations.value,
      origin: 'manual',
    })
  }
  if (res.success) {
    if (res.family) currentFamily.value = { ...currentFamily.value, ...res.family }
    if (res.version) {
      const idx = sourceVersions.value.findIndex((v) => v.id === res.version.id)
      if (idx >= 0) sourceVersions.value[idx] = res.version
      else if (res.version.id) {
        sourceVersions.value = [...sourceVersions.value, res.version]
        currentSourceVersionId.value = res.version.id
      }
    } else {
      await fetchSourceVersions()
    }
    ocrParsedBaseline.value = ocrEditableText.value
    familySourceDirty.value = false
    showToast('原文已保存', 'success')
    await syncPersonDetailsFromSourceQuiet()
  } else {
    showToast(res.message || res.detail || '保存失败', 'error')
  }
}

async function parseTextContent(text: string, opts?: { relationText?: string; rawText?: string }) {
  const res = await api('POST', '/ocr/parse', {
    text: opts?.rawText || text,
    relation_text: opts?.relationText || undefined,
    skip_describe: Boolean(opts?.relationText),
    parse: parseConfig.value,
  }, API_TIMEOUT_LONG)
  if (res.success === false) {
    throw new Error(res.error || res.detail || '解析失败')
  }
  let persons = res.persons || []
  let relations = res.relations || []
  let stats = res.genealogy_stats || null
  let treeNodes = res.tree_preview?.nodes || []

  if (!stats) {
    const built = await api('POST', '/agent/generate', { text, persons, relations })
    if (built.success) {
      persons = built.persons || persons
      relations = built.relations || relations
      stats = built.stats
      treeNodes = built.tree?.nodes || []
    }
  }
  return {
    persons,
    relations,
    stats,
    treeNodes,
    validation: res.validation,
    relationDescription: res.relation_description || '',
    parseSteps: res.parse_steps || [],
    warning: res.warning || '',
  }
}

function applyParseResult(parsed: {
  persons: any[]
  relations: any[]
  stats?: any
  treeNodes?: any[]
  validation?: any
  relationDescription?: string
  parseSteps?: string[]
  warning?: string
}) {
  if (parsed.relationDescription) {
    ocrRelationDescription.value = parsed.relationDescription
  }
  if (parsed.parseSteps?.length) {
    ocrParseSteps.value = parsed.parseSteps
  }
  parsedRelations.value = parsed.relations
  parsedPersons.value = mapParsedPersons(parsed.persons)
  genealogyStats.value = parsed.stats || null
  treePreviewNodes.value = parsed.treeNodes || []
  scanValidation.value = parsed.validation?.persons || parsed.validation || null
  pendingTextRelations.value = normalizeRelationsForBatch(parsed.relations)
}

function adoptRelationDescription() {
  if (!ocrRelationDescription.value.trim()) return
  ocrEditableText.value = ocrRelationDescription.value
  showToast('已采用关系描述稿为左侧校对原文', 'success')
}

async function copyRelationDescription() {
  try {
    await navigator.clipboard.writeText(ocrRelationDescription.value)
    showToast('已复制关系描述稿', 'success')
  } catch {
    showToast('复制失败', 'error')
  }
}

async function previewParseImportDiff(
  familyId: string,
  parsedPersons: any[],
  parsedRelations: any[],
) {
  const res = await api('POST', `/families/${familyId}/parse-import/preview`, {
    persons: mapParsedPersons(parsedPersons),
    relations: normalizeRelationsForBatch(parsedRelations),
  })
  if (res.success === false) {
    throw new Error(res.error || res.detail || '差异对比失败')
  }
  return res.compare as SourceCompareData
}

function openParseImportCompare(
  familyId: string,
  compare: SourceCompareData,
  parsedPersons: any[],
  parsedRelations: any[],
) {
  const detail = (compare as any).persons_to_add_detail as any[] | undefined
  pendingParseImport.value = {
    familyId,
    persons: detail?.length
      ? detail.map((p) => ({ ...p, review_status: p.review_status || 'pending_review' }))
      : mapParsedPersons(parsedPersons.filter((p) => compare.persons_to_add?.includes(p.name))),
    relations: compare.relations_to_add || [],
  }
  sourceCompareData.value = compare
  sourceCompareMode.value = 'parse'
  parseImportPersonsToAdd.value = compare.persons_to_add_count ?? compare.persons_to_add?.length ?? 0
  rebuildRelationsToAdd.value = compare.relations_to_add_count ?? compare.relations_to_add?.length ?? 0
  showSourceCompare.value = true
}

async function applyTextParseToFamily() {
  if (!currentFamily.value?.id || !ocrEditableText.value.trim()) return
  ocrReparsing.value = true
  textParseFailedHint.value = ''
  try {
    const parsed = await parseTextContent(ocrEditableText.value)
    pendingTextRelations.value = normalizeRelationsForBatch(parsed.relations)
    const personCount = parsed.persons?.length || 0
    if (parsed.relationDescription) {
      ocrRelationDescription.value = parsed.relationDescription
      ocrParseSteps.value = parsed.parseSteps || ['describe', 'digitize']
    }

    await api('PUT', `/families/${currentFamily.value.id}/source-text`, {
      source_text: ocrEditableText.value,
      source_annotations: ocrAnnotations.value,
    })

    if (parsed.warning) {
      showToast(parsed.warning, 'error')
    }

    if (personCount === 0) {
      textParseFailedHint.value = '自动解析未识别到成员。您已梳理的原文已保存，可直接用 AI 对话整理继续建谱。'
      showToast('解析未得到成员，请改用 AI 对话整理', 'error')
      return
    }

    applyParseResult(parsed)
    const compare = await previewParseImportDiff(
      currentFamily.value.id,
      parsed.persons,
      parsed.relations,
    )
    openParseImportCompare(currentFamily.value.id, compare, parsed.persons, parsed.relations)
    ocrParsedBaseline.value = ocrEditableText.value
  } catch (e: any) {
    textParseFailedHint.value = '自动解析失败，但原文仍可保存。请点「改用 AI 对话整理」继续。'
    try {
      await api('PUT', `/families/${currentFamily.value!.id}/source-text`, {
        source_text: ocrEditableText.value,
        source_annotations: ocrAnnotations.value,
      })
    } catch {
      /* ignore save error in fallback path */
    }
    showToast((e.message || '解析失败') + '，可改用 AI 对话整理', 'error')
  } finally {
    ocrReparsing.value = false
  }
}

async function createRelationFromNames(payload: { from: string; to: string }) {
  relationLinkFromName.value = null
  const rel = {
    from: payload.from,
    to: payload.to,
    type: 'parent_child',
    status: 'confirmed',
  }

  if (!currentFamily.value?.id) {
    parsedRelations.value = [...parsedRelations.value, rel]
    showToast(`已记录关系 ${payload.from} → ${payload.to}，保存时一并入库`, 'success')
    return
  }

  const fromP = persons.value.find((p) => p.name === payload.from)
  const toP = persons.value.find((p) => p.name === payload.to)
  if (!fromP || !toP) {
    pendingTextRelations.value = [...pendingTextRelations.value, rel]
    showToast('请先确保两人在族谱中，或先「AI 解析并合并」', 'info')
    return
  }

  const res = await api('POST', '/relations', {
    family_id: currentFamily.value.id,
    from_person_id: fromP.id,
    to_person_id: toP.id,
    relation_type: 'parent_child',
    status: 'confirmed',
  })
  if (res.success === false) {
    showToast(res.detail || res.message || '建立关系失败', 'error')
    return
  }
  showToast(`已建立 ${payload.from} → ${payload.to}`, 'success')
  await fetchPersons()
  await fetchRelations()
  await loadTree()
}

async function applySingleTextRelation(r: any) {
  if (!currentFamily.value?.id) return
  const fromP = persons.value.find((p) => p.name === r.from)
  const toP = persons.value.find((p) => p.name === r.to)
  if (!fromP || !toP) {
    showToast(`请先入库「${r.from}」和「${r.to}」`, 'info')
    return
  }
  const res = await api('POST', '/relations', {
    family_id: currentFamily.value.id,
    from_person_id: fromP.id,
    to_person_id: toP.id,
    relation_type: r.type || 'parent_child',
    status: r.status || 'confirmed',
  })
  if (res.success !== false) {
    pendingTextRelations.value = pendingTextRelations.value.filter((x) => x !== r)
    await fetchPersons()
    await fetchRelations()
    await loadTree()
    showToast('关系已应用', 'success')
  }
}

function openFamilyEdit() {
  if (!currentFamily.value) return
  familyForm.value = {
    name: currentFamily.value.name || '',
    surname: currentFamily.value.surname || '',
    description: currentFamily.value.description || '',
    start_generation: currentFamily.value.start_generation || 1,
    root_person_id: currentFamily.value.root_person_id || '',
  }
  showFamilyModal.value = true
}

async function recalculateGenerations() {
  if (!currentFamily.value?.id) return
  const res = await api('POST', `/families/${currentFamily.value.id}/recalculate-generations`)
  if (res.success) {
    showToast(
      res.unresolved_count
        ? `世代已重算，${res.unresolved_count} 人未能连到始祖`
        : '世代已重算',
      res.unresolved_count ? 'info' : 'success',
    )
    currentFamily.value = {
      ...currentFamily.value,
      root_person_id: res.root_person_id,
      start_generation: res.start_generation,
    }
    await fetchPersons()
    await loadTree()
  } else {
    showToast(res.message || res.detail || '重算失败', 'error')
  }
}

async function saveFamily() {
  if (!currentFamily.value?.id || !familyForm.value.name) return
  const payload = {
    ...familyForm.value,
    root_person_id: familyForm.value.root_person_id || null,
    start_generation: familyForm.value.start_generation || 1,
  }
  const res = await api('PUT', `/families/${currentFamily.value.id}`, payload)
  if (res.success) {
    currentFamily.value = { ...currentFamily.value, ...res.family }
    showFamilyModal.value = false
    await fetchFamilies()
    await fetchPersons()
    await loadTree()
    showToast('族谱设置已保存', 'success')
  } else {
    showToast(res.message || res.detail || '保存失败', 'error')
  }
}

function openPersonFromDetail(p: any) {
  personDetail.value = null
  viewPersonDetail(p)
}

async function loadTree() {
  if (!currentFamily.value?.id) return
  const res = await api('GET', `/families/${currentFamily.value.id}/tree?style=${treeStyle.value}`)
  treeNodes.value = res.nodes || []
  if (res.bounds?.width && res.bounds?.height) {
    treeBounds.value = res.bounds
  } else {
    computeTreeBoundsLocal()
  }
  await nextTick()
  fitTreeToView()
}

function computeTreeBoundsLocal() {
  let maxX = 0
  let maxY = 0
  for (const p of treeNodes.value) {
    const l = p.layout || {}
    const w = l.node_width || 128
    const h = l.node_height || 72
    maxX = Math.max(maxX, (l.offset_x || 0) + w)
    maxY = Math.max(maxY, (l.offset_y || 0) + h)
  }
  treeBounds.value = {
    width: Math.max(maxX + 64 + (treeStyle.value === 'silkworm' ? SILKWORM_LABEL_COL : 0), 480),
    height: Math.max(maxY + 64, 360),
  }
}

const treeViewSizeStyle = computed(() => {
  if (!isAbsoluteTreeLayout.value) return {}
  return {
    width: `${treeDisplayWidth.value}px`,
    height: `${treeBounds.value.height}px`,
  }
})

function personName(id: string | null) {
  if (!id) return ''
  return persons.value.find((p) => p.id === id)?.name || ''
}

function toggleRelationLinkMode() {
  relationLinkMode.value = !relationLinkMode.value
  relationLinkFromId.value = null
}

function onTreeNodeClick(p: any, e: MouseEvent) {
  if (relationLinkMode.value || e.shiftKey) {
    if (!relationLinkFromId.value) {
      relationLinkFromId.value = p.id
      selectPerson(p.id, { focusOnTree: false })
      showToast(`已选「${p.name}」，请点击另一成员建立关系`, 'info')
      return
    }
    if (relationLinkFromId.value === p.id) {
      relationLinkFromId.value = null
      return
    }
    void promptTreeRelation(relationLinkFromId.value, p.id)
    return
  }
  selectPerson(p.id, { focusOnTree: false })
}

async function promptTreeRelation(fromId: string, toId: string) {
  const a = persons.value.find((p) => p.id === fromId)
  const b = persons.value.find((p) => p.id === toId)
  if (!a || !b || !currentFamily.value?.id) return
  const asParentChild = confirm(
    `建立关系：\n「确定」= ${a.name} 为父/母 → ${b.name} 为子女\n「取消」= ${a.name} 与 ${b.name} 为配偶`,
  )
  const res = await api('POST', '/relations', {
    family_id: currentFamily.value.id,
    from_person_id: fromId,
    to_person_id: toId,
    relation_type: asParentChild ? 'parent_child' : 'spouse',
    status: 'confirmed',
  })
  relationLinkFromId.value = null
  if (res.success === false) {
    showToast(res.detail || res.message || '建立关系失败', 'error')
    return
  }
  showToast(`已建立 ${a.name} → ${b.name}`, 'success')
  await fetchPersons()
  await fetchRelations()
  await loadTree()
}

function treeNodeStyle(p: any) {
  const layout = p.layout || {}
  const nodeW = layout.node_width || (treeCompact.value ? 96 : 128)
  const labelOffset = treeStyle.value === 'silkworm' ? SILKWORM_LABEL_COL : 0
  if (treeStyle.value === 'silkworm' || treeStyle.value === 'radial') {
    return {
      position: 'absolute',
      left: (layout.offset_x || 0) + labelOffset + 'px',
      top: (layout.offset_y || 0) + 'px',
      width: nodeW + 'px',
    }
  }
  if (treeStyle.value === 'eu') {
    return { marginLeft: (layout.offset_x || 0) + 'px', marginTop: (layout.offset_y || 0) + 'px' }
  }
  return { marginLeft: ((layout.offset_x || 0) + (p.depth || 0) * 24) + 'px', marginTop: '6px' }
}

function editPersonById(id: string) {
  const p = persons.value.find(x => x.id === id)
  if (p) editPerson(p)
}

function addChildById(id: string) {
  const p = persons.value.find(x => x.id === id)
  if (p) addChild(p)
}

async function doSearch() {
  if (!currentFamily.value?.id) return
  searchLoading.value = true
  try {
    const res = await api('POST', `/families/${currentFamily.value.id}/search`, {
      q: searchQuery.value,
      mode: searchMode.value,
      use_ai: searchMode.value === 'nl',
    })
    searchResults.value = res.results || []
  } finally {
    searchLoading.value = false
  }
}

async function viewPersonDetail(p: any) {
  const q = currentSourceVersionId.value ? `?source_version_id=${encodeURIComponent(currentSourceVersionId.value)}` : ''
  const res = await api('GET', `/persons/${p.id}${q}`)
  if (res.success) personDetail.value = res
}

async function syncPersonDetailsFromSourceQuiet() {
  if (!currentFamily.value?.id || syncPersonDetailsLoading.value) return
  if (!activeSourceText.value?.trim()) return
  try {
    const res = await api('POST', `/families/${currentFamily.value.id}/sync-person-details`, {
      source_version_id: currentSourceVersionId.value || undefined,
    })
    if (res.success && (res.persons_updated ?? 0) > 0) {
      await fetchPersons()
      if (selectedPersonId.value) {
        const p = persons.value.find((x) => x.id === selectedPersonId.value)
        if (p) await viewPersonDetail(p)
      }
    }
  } catch {
    /* ignore background sync */
  }
}

async function syncPersonDetailsFromSource() {
  if (!currentFamily.value?.id || syncPersonDetailsLoading.value) return
  if (!activeSourceText.value.trim()) {
    showToast('请先保存文字版原文', 'info')
    return
  }
  syncPersonDetailsLoading.value = true
  try {
    const res = await api('POST', `/families/${currentFamily.value.id}/sync-person-details`, {
      source_version_id: currentSourceVersionId.value || undefined,
    })
    if (!res.success) {
      showToast(res.error || res.detail || '补全失败', 'error')
      return
    }
    const n = res.persons_updated ?? 0
    showToast(n > 0 ? `已从文字版补全 ${n} 名成员资料` : '未发现可补全的空字段（姓名需与文字版一致）', n > 0 ? 'success' : 'info')
    await fetchPersons()
    if (selectedPersonId.value) {
      const p = persons.value.find((x) => x.id === selectedPersonId.value)
      if (p) await viewPersonDetail(p)
    }
  } catch {
    showToast('补全失败，请确认后端已启动', 'error')
  } finally {
    syncPersonDetailsLoading.value = false
  }
}

function exportPDF() {
  if (!currentFamily.value?.id) return
  window.open(`/api/families/${currentFamily.value.id}/export/pdf?style=${treeStyle.value}`, '_blank')
}

function relationStroke(r: any) {
  if (r.status === 'disputed') return '#b33'
  if (r.status === 'inferred') return '#C9A961'
  return '#8B6F47'
}

function relationDash(r: any) {
  if (r.status === 'disputed') return '4,4'
  if (r.status === 'inferred') return '6,3'
  return ''
}

function relationWidth(r: any) {
  return r.relation_type === 'spouse' ? 1.5 : 2
}

async function fetchPersons() {
  if (!currentFamily.value?.id) return
  persons.value = await api('GET', `/families/${currentFamily.value.id}/persons`)
}

async function fetchRelations() {
  if (!currentFamily.value?.id) return
  relations.value = await api('GET', `/families/${currentFamily.value.id}/relations`)
}

// ==================== 浜虹墿鎿嶄綔 ====================

function resetPersonForm() {
  const maxGen = persons.value.length
    ? Math.max(...persons.value.map(p => p.generation || 1))
    : 0
  personForm.value = {
    name: '', gender: 'unknown', birth_year: null, death_year: null,
    generation: maxGen || 1,
    generation_name: '', generation_prefix: '', parent_id: '',
    courtesy_name: '', art_name: '', county: '', town: '', village: '',
    biography: '', spouse_id: '', review_status: 'confirmed',
  }
}

function addChild(parent: any) {
  editingPerson.value = null
  personForm.value = {
    name: '', gender: 'unknown', birth_year: null, death_year: null,
    generation: (parent.generation || 1) + 1, generation_name: '',
    generation_prefix: '', parent_id: parent.id,
    courtesy_name: '', art_name: '', county: '', town: '', village: '',
    biography: '', spouse_id: '', review_status: 'confirmed',
  }
  showPersonModal.value = true
}

async function addKinship(anchor: any, kinship: string) {
  if (!currentFamily.value?.id || !anchor?.id) return
  const name = window.prompt(`请输入「${anchor.name}」的${kinship}姓名`)
  if (!name?.trim()) return
  const res = await api('POST', `/families/${currentFamily.value.id}/persons/kinship`, {
    anchor_id: anchor.id,
    kinship,
    person: { name: name.trim(), gender: 'unknown', review_status: 'pending_review' },
  })
  if (res.success === false) {
    showToast(res.message || res.detail || '添加失败', 'error')
    return
  }
  const hint = res.placeholders_added
    ? `已添加第 ${res.target_generation} 代，补全 ${res.placeholders_added} 个占位代际`
    : `已添加第 ${res.target_generation} 代`
  showToast(hint, 'success')
  await fetchPersons()
  await fetchRelations()
  expandAllNav()
  await loadTree()
  if (res.id) selectedPersonId.value = res.id
}

function editPerson(p: any) {
  const latest = persons.value.find((x) => x.id === p.id) || p
  editingPerson.value = latest
  personForm.value = {
    ...latest,
    parent_id: latest.parent_id || '',
    spouse_id: latest.spouse_id || '',
    review_status: latest.review_status || 'confirmed',
  }
  showPersonModal.value = true
}

async function savePerson() {
  if (!validatePersonForm()) return
  const data = {
    ...personForm.value,
    name: personForm.value.name.trim(),
    family_id: currentFamily.value!.id,
    parent_id: personForm.value.parent_id || null,
    spouse_id: personForm.value.spouse_id || null,
  }

  let res
  if (editingPerson.value?.id) {
    res = await api('PUT', `/persons/${editingPerson.value.id}`, data)
  } else {
    res = await api('POST', '/persons', data)
  }

  if (res.success === false) {
    showToast(res.message || res.detail || '保存失败', 'error')
    return
  }

  saveSuccessHint.value = '✓ 保存成功'
  showToast('保存成功', 'success')
  const savedId = res.person?.id || editingPerson.value?.id
  await fetchPersons()
  await fetchRelations()
  expandAllNav()
  await loadTree()
  if (savedId) selectedPersonId.value = savedId
  window.setTimeout(() => {
    saveSuccessHint.value = ''
    showPersonModal.value = false
    editingPerson.value = null
  }, 1200)
}

async function deletePersonFromModal() {
  if (!editingPerson.value?.id) return
  if (!confirm(`确定删除「${editingPerson.value.name}」？相关关系将一并删除`)) return
  showPersonModal.value = false
  await deletePerson(editingPerson.value.id)
  editingPerson.value = null
}

async function addRelation() {
  if (!newRelation.value.from_person_id || !newRelation.value.to_person_id) {
    alert('请选择关系的双方成员')
    return
  }
  const res = await api('POST', '/relations', {
    family_id: currentFamily.value!.id,
    ...newRelation.value,
  })
  if (!res.success) {
    alert(res.detail || res.message || '添加失败')
    return
  }
  newRelation.value.from_person_id = ''
  newRelation.value.to_person_id = ''
  await fetchPersons()
  await fetchRelations()
  await loadTree()
}

async function updateRelationStatus(relationId: string, status: string) {
  await api('PUT', `/relations/${relationId}`, { status })
  await fetchRelations()
  await loadTree()
}

async function removeRelation(relationId: string) {
  if (!confirm('删除这条关系？')) return
  await api('DELETE', `/relations/${relationId}`)
  await fetchPersons()
  await fetchRelations()
  await loadTree()
}

async function deletePerson(id: string) {
  if (!confirm('确定删除？')) return
  await api('DELETE', `/persons/${id}`)
  await fetchPersons()
  await fetchRelations()
  await loadTree()
}

// ==================== OCR ====================

function goOCR() {
  showOCR.value = true
  currentFamily.value = null
  ocrStep.value = 'select'
  previewImage.value = ''
  ocrResult.value = { text: '' }
  ocrEditableText.value = ''
  ocrParsedBaseline.value = ''
  ocrAnnotations.value = []
  ocrRelationDescription.value = ''
  ocrCustomText.value = ''
  ocrVersionTab.value = 'v1'
  ocrDescribingV2.value = false
  ocrParseSteps.value = []
  parsedPersons.value = []
  parsedRelations.value = []
  genealogyStats.value = null
  treePreviewNodes.value = []
}

function selectFamilyForOCR(f: any) {
  ocrFamilyId.value = f.id
  ocrStep.value = 'upload'
}

function handleImageSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    previewImage.value = e.target?.result as string
  }
  reader.readAsDataURL(file)
}

async function doOCR() {
  if (!previewImage.value) return
  ocrLoading.value = true
  ocrDescribingV2.value = false
  scanValidation.value = null
  ocrRelationDescription.value = ''
  ocrCustomText.value = ''
  ocrParseSteps.value = []
  parsedPersons.value = []
  parsedRelations.value = []
  pendingTextRelations.value = []
  genealogyStats.value = null
  treePreviewNodes.value = []

  try {
    const base64 = previewImage.value.split(',')[1]

    const ocrRes = await api('POST', '/agent/scan-ocr', {
      image: base64,
      ocr: ocrConfig.value,
    }, API_TIMEOUT_LONG)

    if (!ocrRes.success) {
      alert(ocrRes.error || ocrRes.message || '文字识别失败')
      return
    }

    ocrResult.value = {
      text: ocrRes.text,
      provider: ocrRes.ocr?.provider,
      model: ocrRes.ocr?.model,
    }
    ocrEditableText.value = ocrRes.text || ''
    ocrParsedBaseline.value = ocrRes.text || ''
    ocrAnnotations.value = []
    ocrStep.value = 'result'
    ocrVersionTab.value = 'v1'
    ocrLoading.value = false

    if (ocrRes.text) {
      autoExtractOcrNames()
    }

    await continueOcrRelationDescribe(ocrRes.text || '')
  } catch (err: any) {
    alert(err?.message || '识别失败，请确认后端已启动且 API Key 正确')
  } finally {
    ocrLoading.value = false
    ocrDescribingV2.value = false
  }
}

async function continueOcrRelationDescribe(rawText: string) {
  const text = (rawText || '').trim()
  if (!text) return
  ocrDescribingV2.value = true
  try {
    const parsed = await parseTextContent(text)
    applyParseResult(parsed)
    if (parsed.warning) {
      showToast(parsed.warning, 'error')
    } else if (parsed.relationDescription) {
      showToast('人物关系已整理完成，可切换到「版本二」查看', 'success')
    }
  } catch (e: any) {
    showToast(e.message || '人物关系整理失败', 'error')
  } finally {
    ocrDescribingV2.value = false
  }
}

function mapParsedPersons(persons: any[]) {
  return persons.map((p: any) => ({
    name: p.name,
    gender: p.gender || 'unknown',
    birth_year: p.birth_year || null,
    death_year: p.death_year || null,
    generation: p.generation || 1,
    generation_name: p.generation_name || '',
    review_status: p.review_status || 'pending_review',
    _review_flags: p._review_flags || [],
    ai_confidence: p.ai_confidence,
  }))
}

async function autoExtractOcrNames() {
  if (!ocrEditableText.value.trim()) return
  try {
    const res = await api('POST', '/ocr/extract-names', { text: ocrEditableText.value })
    if (res.success && res.annotations?.length) {
      ocrAnnotations.value = res.annotations
    }
  } catch {
    /* 规则识名失败不影响主流程 */
  }
}

async function reparseFromEditedText() {
  const raw = ocrEditableText.value.trim()
  const rel = digitizeSourceText.value.trim()
  if (!rel) return
  ocrReparsing.value = true
  try {
    const parsed = await parseTextContent(rel, {
      relationText: (ocrCustomText.value.trim() || ocrRelationDescription.value.trim()) || undefined,
      rawText: raw || rel,
    })
    applyParseResult(parsed)
    ocrParsedBaseline.value = ocrEditableText.value
    if (parsed.warning) {
      showToast(parsed.warning, 'error')
    }
  } catch (e: any) {
    showToast(e.message || '解析失败', 'error')
  } finally {
    ocrReparsing.value = false
  }
}

function addAnnotatedPersonToParsed(payload: { name: string; source?: string }) {
  const name = (payload.name || '').trim()
  if (!name) return
  if (parsedPersons.value.some((p) => p.name === name)) {
    showToast(`「${name}」已在待入库列表`, 'info')
    return
  }
  parsedPersons.value.push({
    name,
    gender: 'unknown',
    birth_year: null,
    death_year: null,
    generation: 1,
    generation_name: '',
    review_status: 'pending_review',
  })
  showToast(`已添加「${name}」到待入库`, 'success')
}

async function addAnnotatedPersonToFamily(payload: { name: string; source?: string }) {
  const name = (payload.name || '').trim()
  if (!name || !currentFamily.value?.id) return
  if (persons.value.some((p) => p.name === name)) {
    showToast(`「${name}」已在族谱中`, 'info')
    return
  }
  const parent = displayPerson.value
  const data: Record<string, unknown> = {
    name,
    gender: 'unknown',
    family_id: currentFamily.value.id,
    review_status: 'pending_review',
  }
  if (parent) {
    data.parent_id = parent.id
    data.generation = (parent.generation || 1) + 1
  }
  const res = await api('POST', '/persons', data)
  if (res.success === false) {
    showToast(res.message || res.detail || '添加失败', 'error')
    return
  }
  showToast(parent ? `已将「${name}」挂到「${parent.name}」下` : `已添加「${name}」`, 'success')
  await fetchPersons()
  await fetchRelations()
  expandAllNav()
  await loadTree()
  if (res.id) selectedPersonId.value = res.id
}

function parseNameDragPayload(e: DragEvent): { name: string } | null {
  const raw = e.dataTransfer?.getData(NAME_DRAG_MIME)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function onParsedListDragOver(e: DragEvent) {
  if (e.dataTransfer?.types.includes(NAME_DRAG_MIME)) {
    e.preventDefault()
    parsedListDragOver.value = true
  }
}

function onParsedListDrop(e: DragEvent) {
  parsedListDragOver.value = false
  const data = parseNameDragPayload(e)
  if (data?.name) addAnnotatedPersonToParsed(data)
}

function onTreeDragOver(e: DragEvent) {
  if (currentFamily.value && e.dataTransfer?.types.includes(NAME_DRAG_MIME)) {
    e.preventDefault()
    treeNameDropActive.value = true
  }
}

function onTreeDragLeave() {
  treeNameDropActive.value = false
}

async function onTreeNameDrop(e: DragEvent) {
  treeNameDropActive.value = false
  const data = parseNameDragPayload(e)
  if (data?.name) await addAnnotatedPersonToFamily(data)
}

function editParsedPerson(i: number) {
  parsedEditIndex.value = i
  parsedEditForm.value = { ...parsedPersons.value[i] }
}

function saveParsedEdit() {
  if (parsedEditIndex.value === null) return
  if (!parsedEditForm.value.name?.trim()) {
    alert('请填写姓名')
    return
  }
  parsedPersons.value[parsedEditIndex.value] = { ...parsedEditForm.value }
  parsedEditIndex.value = null
}

async function openAiOrganize(options?: { bootstrap?: boolean }) {
  await fetchAISettings()
  if (currentFamily.value?.id && !activeSourceText.value) {
    await fetchSourceVersions()
  }
  aiOrganizeBootstrap.value = Boolean(options?.bootstrap)
  if (options?.bootstrap) {
    organizeCleanSlate.value = true
    showOrganizeDrawer.value = true
  }
  aiOrganizeInitialPrompt.value = options?.bootstrap
    ? '请根据附带的族谱原文，干净整理出完整主谱：提取所有人物、世代与父子/配偶关系，给出可应用的整理方案。'
    : ''
  showAiOrganize.value = true
}

function closeAiOrganize() {
  showAiOrganize.value = false
  aiOrganizeInitialPrompt.value = ''
  aiOrganizeBootstrap.value = false
}

async function loadOrganizeState(familyId: string) {
  try {
    const res = await api('GET', `/families/${familyId}/ai-organize/state`)
    if (!res.success) return
    pendingOrganizePlan.value = res.pending_plan || null
    pendingOrganizeDiff.value = res.pending_diff ?? null
    organizeApplyMode.value = res.apply_mode === 'replace' ? 'replace' : 'merge'
    organizeCleanSlate.value = Boolean(res.clean_slate)
  } catch {
    /* ignore */
  }
}

async function saveOrganizeState() {
  if (!currentFamily.value?.id) return
  try {
    await api('PUT', `/families/${currentFamily.value.id}/ai-organize/state`, {
      pending_plan: pendingOrganizePlan.value,
      pending_diff: pendingOrganizeDiff.value,
      apply_mode: organizeApplyMode.value,
      clean_slate: organizeCleanSlate.value,
    })
  } catch {
    /* ignore */
  }
}

async function refreshOrganizeDiff() {
  if (!currentFamily.value?.id || !pendingOrganizePlan.value) return
  try {
    const res = await api('POST', `/families/${currentFamily.value.id}/ai-organize/refresh-diff`, {
      plan: pendingOrganizePlan.value,
      clean_slate: organizeCleanSlate.value,
    })
    if (res.success) {
      pendingOrganizePlan.value = res.plan || pendingOrganizePlan.value
      pendingOrganizeDiff.value = res.diff || null
      if (persons.value.length <= 0) {
        organizeApplyMode.value = 'replace'
      } else if (organizeApplyMode.value !== 'merge') {
        organizeApplyMode.value = pickDefaultApplyMode(
          { plan: pendingOrganizePlan.value, diff: pendingOrganizeDiff.value },
          { memberCount: persons.value.length },
        )
      }
      await saveOrganizeState()
    }
  } catch {
    /* ignore */
  }
}

function onOrganizePlanPatch(plan: OrganizePlan) {
  pendingOrganizePlan.value = plan
}

function onOrganizePlanEdited() {
  if (organizePlanEditTimer) clearTimeout(organizePlanEditTimer)
  organizePlanEditTimer = setTimeout(() => {
    void refreshOrganizeDiff()
  }, 450)
}

function onAiPlanUpdate(payload: { plan: OrganizePlan | null; diff: OrganizeDiff | null }) {
  pendingOrganizePlan.value = payload.plan
  pendingOrganizeDiff.value = payload.diff
  if (payload.plan && planHasChanges(payload.plan)) {
    organizeApplyMode.value = pickDefaultApplyMode(payload, { memberCount: persons.value.length })
    showOrganizeDrawer.value = true
    showToast('AI 方案已同步到「族谱整理」面板', 'success')
  }
  void saveOrganizeState()
}

async function dismissOrganizePlan() {
  pendingOrganizePlan.value = null
  pendingOrganizeDiff.value = null
  await saveOrganizeState()
}

async function onOrganizeApplied(stats?: Record<string, number>) {
  pendingOrganizePlan.value = null
  pendingOrganizeDiff.value = null
  organizeApplyMode.value = 'merge'
  await saveOrganizeState()
  await fetchPersons()
  await fetchRelations()
  await loadTree()
  const added = stats?.persons_added ?? 0
  const rels = stats?.relations_added ?? 0
  const diag = stats?.diagnostics as { unmatched_names?: string[]; skipped_relation_count?: number } | undefined
  let msg = added || rels
    ? `主谱已更新（+${added} 人，+${rels} 关系），可在可视化界面继续微调`
    : '主谱已更新，可在可视化界面继续微调'
  if (diag?.unmatched_names?.length) {
    msg += `；未匹配姓名：${diag.unmatched_names.slice(0, 5).join('、')}`
  } else if (diag?.skipped_relation_count) {
    msg += `；${diag.skipped_relation_count} 条关系未写入（已存在或姓名未匹配）`
  }
  showToast(msg, 'success')
}

watch(showOrganizeDrawer, (open) => {
  if (open && pendingOrganizePlan.value && planHasChanges(pendingOrganizePlan.value)) {
    void refreshOrganizeDiff()
  }
})

async function onOrganizeCleared() {
  selectedPersonId.value = null
  organizeCleanSlate.value = true
  organizeApplyMode.value = 'replace'
  await fetchPersons()
  await fetchRelations()
  await loadTree()
  if (pendingOrganizePlan.value && planHasChanges(pendingOrganizePlan.value)) {
    await refreshOrganizeDiff()
    showOrganizeDrawer.value = true
    showToast('主谱已清空，可点「替换写入主谱」直接写入 AI 方案', 'success')
  } else {
    showToast('主谱已清空，可从原文或 AI 方案重建', 'success')
  }
}

watch([organizeApplyMode, organizeCleanSlate], () => {
  void saveOrganizeState()
})

async function rebuildFamily() {
  if (!currentFamily.value?.id) return
  buildLoading.value = true
  buildStats.value = null
  sourceCompareMode.value = 'source'
  try {
    const res = await api('POST', `/families/${currentFamily.value.id}/rebuild`, { dry_run: true })
    if (!res.success) {
      alert(res.error || '整理失败')
      return
    }
    const compare = (res.compare || null) as SourceCompareData | null
    if (compare && !compare.proposed_relations?.length && res.proposed_relations?.length) {
      compare.proposed_relations = res.proposed_relations
    }
    sourceCompareData.value = compare
    rebuildRelationsToAdd.value =
      res.rebuild?.relations_added ?? compare?.proposed_relations?.length ?? 0
    rebuildPersonDetailsToAdd.value =
      res.rebuild?.person_details_to_update ?? res.person_detail_patches?.length ?? 0
    showSourceCompare.value = true
  } catch {
    alert('整理失败，请确认后端已启动')
  } finally {
    buildLoading.value = false
  }
}

function closeSourceCompare() {
  showSourceCompare.value = false
  pendingParseImport.value = null
  sourceCompareMode.value = 'source'
}

function openSourceFromCompare() {
  showSourceCompare.value = false
  showTextImportDrawer.value = true
}

async function applyFromSourceCompare() {
  if (sourceCompareMode.value === 'parse') {
    await applyParseImportFromCompare()
    return
  }
  await applyRebuildFromCompare()
}

async function applyParseImportFromCompare() {
  const pending = pendingParseImport.value
  if (!pending?.familyId) return
  if (!pending.persons.length && !pending.relations.length) {
    showToast('无新增项可入库', 'info')
    closeSourceCompare()
    return
  }
  try {
    const batch = await api('POST', '/persons/batch', {
      family_id: pending.familyId,
      persons: pending.persons,
      relations: normalizeRelationsForBatch(pending.relations),
      merge: true,
    })
    if (batch.success === false) {
      showToast(batch.message || batch.detail || '入库失败', 'error')
      return
    }
    closeSourceCompare()
    showToast(`已加入主谱 ${batch.count ?? pending.persons.length} 人、${batch.relation_count ?? 0} 条关系`, 'success')
    if (showOCR.value && ocrFamilyId.value === pending.familyId) {
      showOCR.value = false
      parsedPersons.value = []
      parsedRelations.value = []
      pendingTextRelations.value = []
      relationLinkFromName.value = null
      await viewFamily(pending.familyId)
    } else if (currentFamily.value?.id === pending.familyId) {
      await fetchPersons()
      await fetchRelations()
      expandAllNav()
      await loadTree()
    }
  } catch {
    showToast('入库失败，请确认后端已启动', 'error')
  }
}

async function applyRebuildFromCompare() {
  if (!currentFamily.value?.id) return
  if (rebuildRelationsToAdd.value <= 0 && rebuildPersonDetailsToAdd.value <= 0) return
  showSourceCompare.value = false
  buildLoading.value = true
  buildStats.value = null
  try {
    const res = await api('POST', `/families/${currentFamily.value.id}/rebuild`, {
      source_version_id: currentSourceVersionId.value || undefined,
    })
    if (!res.success) {
      alert(res.error || '整理失败')
      return
    }
    buildStats.value = res.stats
    const added = res.rebuild?.relations_added ?? 0
    const updated = res.rebuild?.persons_updated ?? 0
    if (added > 0 || updated > 0) {
      showToast(`已补全 ${added} 条关系、${updated} 名成员资料`, 'success')
    } else {
      showToast('未发现可补全项', 'info')
    }
    await fetchPersons()
    await fetchRelations()
    await loadTree()
    if (selectedPersonId.value) {
      const p = persons.value.find((x) => x.id === selectedPersonId.value)
      if (p) await viewPersonDetail(p)
    }
  } catch {
    alert('整理失败，请确认后端已启动')
  } finally {
    buildLoading.value = false
  }
}

function normalizeRelationsForBatch(rels: any[]) {
  return rels
    .map((r) => ({
      from: r.from || r.from_name || '',
      to: r.to || r.to_name || '',
      type: r.type || r.relation_type || 'parent_child',
      status: r.status || 'inferred',
      confidence: r.confidence,
    }))
    .filter((r) => r.from && r.to)
}

async function saveParsedPersons() {
  if (!ocrEditableText.value.trim() && !digitizeSourceText.value.trim() && !parsedPersons.value.length) return

  const activeKind = ocrCustomText.value.trim()
    ? 'custom'
    : ocrRelationDescription.value.trim()
      ? 'relation_desc'
      : 'ocr_raw'

  await api('POST', `/families/${ocrFamilyId.value}/source-versions/save-ocr-pipeline`, {
    ocr_text: ocrEditableText.value,
    relation_description: ocrRelationDescription.value,
    custom_text: ocrCustomText.value,
    source_annotations: ocrAnnotations.value,
    active_kind: activeKind,
  })

  if (parsedPersons.value.length) {
    try {
      const compare = await previewParseImportDiff(
        ocrFamilyId.value,
        parsedPersons.value,
        [...parsedRelations.value, ...pendingTextRelations.value],
      )
      openParseImportCompare(
        ocrFamilyId.value,
        compare,
        parsedPersons.value,
        [...parsedRelations.value, ...pendingTextRelations.value],
      )
      return
    } catch (e: any) {
      showToast(e.message || '差异对比失败', 'error')
      return
    }
  }

  showToast('原文已保存到族谱', 'success')
  showOCR.value = false
  parsedPersons.value = []
  parsedRelations.value = []
  pendingTextRelations.value = []
  relationLinkFromName.value = null
  await viewFamily(ocrFamilyId.value)
}

// ==================== 瀵煎嚭瀵煎叆 ====================

async function exportJSON() {
  const data = await api('GET', `/families/${currentFamily.value.id}/export`)
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${currentFamily.value.name || '族谱'}.json`
  a.click()
}

function handleImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = async (e) => {
    try {
      const data = JSON.parse(e.target?.result as string)
      await api('POST', '/import', data)
      fetchFamilies()
      if (currentFamily.value?.id === data.family?.id) {
        await fetchPersons()
        await fetchRelations()
      }
    } catch {
      alert('导入失败')
    }
  }
  reader.readAsText(file)
}

// ==================== 鍥惧舰杈呭姪 ====================

function getGenderColor(gender: string) {
  return gender === 'male' ? '#8B6F47' : gender === 'female' ? '#D48C4A' : '#C9A961'
}

function getNodeX(id: string) {
  const idx = persons.value.findIndex(p => p.id === id)
  return 80 + (idx % 4) * 180
}

function getNodeY(id: string) {
  const idx = persons.value.findIndex(p => p.id === id)
  return 80 + Math.floor(idx / 4) * 100
}

// ==================== AI 璁剧疆 ====================

async function fetchAISettings() {
  try {
    const res = await api('GET', '/ai/config')
    if (res.ocr) ocrConfig.value = { ...ocrConfig.value, ...res.ocr }
    if (res.parse) parseConfig.value = { ...parseConfig.value, ...res.parse }
    if (res.keys) {
      for (const [pid, info] of Object.entries(res.keys as Record<string, any>)) {
        if (!providerKeys.value[pid]) {
          providerKeys.value[pid] = { api_key: '', api_base: info.api_base || '', group_id: '', configured: false }
        }
        providerKeys.value[pid].configured = info.configured
        if (info.api_base) providerKeys.value[pid].api_base = info.api_base
        if (info.group_id) providerKeys.value[pid].group_id = info.group_id
      }
    }
  } catch {}
}

function buildTestPayload(task: 'key' | 'ocr' | 'parse') {
  const payload: Record<string, string> = { task }
  if (task === 'key') {
    payload.provider = keyTab.value
    if (keyTab.value === 'minimax') {
      payload.model = 'MiniMax-M2.7'
    } else {
      const p = providers.value.find(item => item.id === keyTab.value)
      payload.model = p?.text_models?.[0] || p?.text_model || parseConfig.value.model
    }
  } else if (task === 'ocr') {
    payload.provider = ocrConfig.value.provider
    payload.model = ocrConfig.value.model
  } else {
    payload.provider = parseConfig.value.provider
    payload.model = parseConfig.value.model
  }
  const pk = providerKeys.value[payload.provider]
  if (pk?.api_key) payload.api_key = pk.api_key
  if (pk?.group_id) payload.group_id = pk.group_id
  if (payload.provider === 'custom' && pk?.api_base) payload.api_base = pk.api_base
  return payload
}

async function applyTestResult(
  task: 'key' | 'ocr' | 'parse',
  startedAt: number,
  result: { ok: boolean; message: string; preview?: string; latency?: number },
) {
  const elapsed = Date.now() - startedAt
  if (elapsed < TEST_MIN_DISPLAY_MS) {
    await sleep(TEST_MIN_DISPLAY_MS - elapsed)
  }
  testStatus.value[task] = {
    loading: false,
    ok: result.ok,
    message: result.message,
    preview: result.preview || '',
    latency: result.latency || 0,
  }
}

async function testAIModel(task: 'key' | 'ocr' | 'parse') {
  const startedAt = Date.now()
  testStatus.value[task] = { ...emptyTest(), loading: true, message: '连接中…' }

  if (task === 'key' && keyTab.value === 'minimax') {
    const pk = providerKeys.value.minimax
    // 宸蹭繚瀛樿繃閰嶇疆鍒欒蛋鍚庣璇诲簱锛涘惁鍒欒姹傝〃鍗曢噷宸插～
    if (!pk?.configured) {
      if (!pk?.api_key?.trim()) {
        await applyTestResult(task, startedAt, { ok: false, message: '请先填写 API Key' })
        return
      }
      if (!pk?.group_id?.trim()) {
        await applyTestResult(task, startedAt, {
          ok: false,
          message: '请先填写 Group ID（MiniMax 控制台 → 基础信息）',
        })
        return
      }
    }
  }

  try {
    const res = await api('POST', '/ai/test', buildTestPayload(task))
    await applyTestResult(task, startedAt, {
      ok: !!res.success,
      message: res.message || res.error || (res.success ? '连接成功，模型有回应' : '测试失败'),
      preview: res.reply_preview || '',
      latency: res.latency_ms || 0,
    })
  } catch (e: any) {
    await applyTestResult(task, startedAt, {
      ok: false,
      message: e?.message || '请求失败，请确认后端已启动（端口 8080）',
    })
  }
}

async function saveAISettings() {
  const keys: Record<string, { api_key?: string; api_base?: string; group_id?: string }> = {}
  for (const [pid, val] of Object.entries(providerKeys.value)) {
    const entry: { api_key?: string; api_base?: string; group_id?: string } = {}
    if (val.api_key) entry.api_key = val.api_key
    if (pid === 'custom' && val.api_base) entry.api_base = val.api_base
    if (pid === 'minimax' && val.group_id) entry.group_id = val.group_id
    if (Object.keys(entry).length) keys[pid] = entry
  }
  // MiniMax锛欸roup ID 蹇呭～锛屼繚瀛樻椂濮嬬粓鎻愪氦
  const mm = providerKeys.value.minimax
  if (mm) {
    keys.minimax = { ...(keys.minimax || {}), group_id: mm.group_id || '' }
  }
  await api('POST', '/ai/config', {
    keys,
    ocr: ocrConfig.value,
    parse: parseConfig.value,
  })
  showSettings.value = false
  alert('AI 配置已保存')
  await fetchAISettings()
}

watch(showTextImportDrawer, (open) => {
  if (!open) nextTick(() => fitTreeToView())
})

onMounted(async () => {
  fetchFamilies()
  await fetchProviders()
  await fetchAISettings()
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onCanvasPanMove)
  window.removeEventListener('mouseup', onCanvasPanEnd)
})
</script>
