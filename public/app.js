/**
 * ⚽ 2026 世界杯预测系统 - 前端逻辑
 */

const API = '';

// =============================================
// 工具函数
// =============================================
async function api(path, options = {}) {
  const url = API + path;
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options
  };
  if (options.body) config.body = JSON.stringify(options.body);
  const res = await fetch(url, config);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

function $(id) { return document.getElementById(id); }

// 🇺🇳 48队国旗 emoji 映射
const FLAGS = {
  '阿根廷':'🇦🇷','法国':'🇫🇷','巴西':'🇧🇷','英格兰':'🏴󠁧󠁢󠁥󠁮󠁧󠁿','德国':'🇩🇪','西班牙':'🇪🇸','葡萄牙':'🇵🇹','荷兰':'🇳🇱',
  '比利时':'🇧🇪','乌拉圭':'🇺🇾','克罗地亚':'🇭🇷','美国':'🇺🇸','摩洛哥':'🇲🇦','哥伦比亚':'🇨🇴','墨西哥':'🇲🇽','日本':'🇯🇵',
  '瑞典':'🇸🇪','瑞士':'🇨🇭','挪威':'🇳🇴','加拿大':'🇨🇦','塞内加尔':'🇸🇳','厄瓜多尔':'🇪🇨','科特迪瓦':'🇨🇮','奥地利':'🇦🇹',
  '捷克':'🇨🇿','韩国':'🇰🇷','澳大利亚':'🇦🇺','苏格兰':'🏴󠁧󠁢󠁳󠁣󠁴󠁿','埃及':'🇪🇬','伊朗':'🇮🇷','阿尔及利亚':'🇩🇿','加纳':'🇬🇭',
  '土耳其':'🇹🇷','巴拉圭':'🇵🇾','波黑':'🇧🇦','南非':'🇿🇦','卡塔尔':'🇶🇦','刚果(金)':'🇨🇩','巴拿马':'🇵🇦','乌兹别克斯坦':'🇺🇿',
  '约旦':'🇯🇴','海地':'🇭🇹','伊拉克':'🇮🇶','突尼斯':'🇹🇳','沙特阿拉伯':'🇸🇦','佛得角':'🇨🇻','新西兰':'🇳🇿','库拉索':'🇨🇼',
};
function flag(name) { return FLAGS[name] || '🌍'; }

function showToast(msg, type = 'info') {
  const old = document.querySelector('.toast');
  if (old) old.remove();
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

function loading(container, msg = '加载中...') {
  container.innerHTML = `<div class="loading"><div class="spinner"></div><div>${msg}</div></div>`;
}

function formatDate(d) {
  const date = new Date(d);
  return `${date.getMonth()+1}/${date.getDate()}`;
}

// =============================================
// Tab 切换
// =============================================
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

// =============================================
// 初始化
// =============================================
async function init() {
  try {
    const status = await api('/api/status');
    $('statusBadge').textContent = `📅 ${status.meta.updatedAt.slice(0,10)} | ${status.completedCount}场已赛`;
    
    // 加载各 tab 数据
    await Promise.all([
      loadOverview(),
      loadTeamEdit(),
      loadMatchList(),
      loadConfig(),
      loadHistory(),
      loadEloRanking(),
      loadKnockout(),
      loadReview()
    ]);
    
    // 填充球队下拉
    const teams = await api('/api/teams');
    populateTeamSelects(teams);
    
  } catch (e) {
    console.error('初始化失败:', e);
    showToast('连接后端失败，请确保 server.mjs 已启动', 'error');
  }
}

function populateTeamSelects(teams) {
  const groupSelect = $('matchGroup');
  const groups = {};
  for (const t of teams) {
    if (!groups[t.group]) groups[t.group] = [];
    groups[t.group].push(t.name);
  }
  
  // 小组下拉
  groupSelect.innerHTML = '<option value="">选择小组</option>';
  for (const [g, ts] of Object.entries(groups).sort()) {
    groupSelect.innerHTML += `<option value="${g}">Group ${g}</option>`;
  }
  
  // 主客队下拉
  const homeSel = $('matchHome'), awaySel = $('matchAway');
  const predHome = $('predHome'), predAway = $('predAway');
  const opts = teams.map(t => `<option value="${t.name}">${t.name}</option>`).join('');
  homeSel.innerHTML = '<option value="">主队</option>' + opts;
  awaySel.innerHTML = '<option value="">客队</option>' + opts;
  predHome.innerHTML = '<option value="">主队</option>' + opts;
  predAway.innerHTML = '<option value="">客队</option>' + opts;
  
  // 小组筛选
  const filter = $('teamGroupFilter');
  filter.innerHTML = '<option value="">全部小组</option>';
  for (const [g, ts] of Object.entries(groups).sort()) {
    filter.innerHTML += `<option value="${g}">Group ${g}</option>`;
  }
}

// =============================================
// TAB 1: 总览
// =============================================
async function loadOverview() {
  try {
    const [status, groupsData] = await Promise.all([
      api('/api/status'),
      api('/api/groups')
    ]);
    
    const stats = status.stats;
    
    // 概览卡片
    $('overviewCards').innerHTML = `
      <div class="stat-card"><span class="num">${stats.total}</span><span class="label">已完赛</span></div>
      <div class="stat-card"><span class="num">${stats.avgGoals}</span><span class="label">场均进球</span></div>
      <div class="stat-card"><span class="num">${stats.homeWinPct}%</span><span class="label">主胜率</span></div>
      <div class="stat-card"><span class="num">${stats.drawPct}%</span><span class="label">平率</span></div>
      <div class="stat-card"><span class="num">${stats.awayWinPct}%</span><span class="label">客胜率</span></div>
      <div class="stat-card"><span class="num">${status.upcomingCount}</span><span class="label">未赛小组赛</span></div>
      <div class="stat-card"><span class="num">${status.knockoutCount}</span><span class="label">淘汰赛</span></div>
    `;
    
    // 小组积分榜
    let html = '';
    for (const [g, data] of Object.entries(groupsData.standings)) {
      const rows = data.teams.map((s, i) => {
        const maxP = Math.max(...data.teams.map(x => x.p), 1);
        const barPct = (s.p / maxP * 100).toFixed(0);
        const rankClass = i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : '';
        return `<tr>
          <td class="${rankClass}">${s.team}</td>
          <td>${s.played}</td>
          <td>${s.w}</td>
          <td>${s.d}</td>
          <td>${s.l}</td>
          <td>${s.gf}</td>
          <td>${s.ga}</td>
          <td>${s.gd > 0 ? '+' : ''}${s.gd}</td>
          <td><strong>${s.p}</strong></td>
          <td><div class="bar-wrap" style="position:relative;width:100%;height:20px;background:var(--border);border-radius:10px;overflow:hidden;"><div class="bar" style="height:100%;background:linear-gradient(90deg,var(--accent-blue),#60a5fa);border-radius:10px;width:${barPct}%"></div><span class="bar-label" style="position:absolute;left:8px;top:2px;font-size:0.7rem;font-weight:600;color:#fff;">${s.p}分</span></div></td>
        </tr>`;
      }).join('');
      html += `<div class="group-card">
        <h3>Group ${g}</h3>
        <table class="group-table"><thead><tr><th>球队</th><th>赛</th><th>胜</th><th>平</th><th>负</th><th>进</th><th>失</th><th>净</th><th>分</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      </div>`;
    }
    $('groupsGrid').innerHTML = html;
    
    // 比分分布
    const scores = Object.entries(stats.scoreDist).slice(0, 10);
    const maxScore = Math.max(...scores.map(([_, c]) => c));
    let scoreHTML = '';
    for (const [sc, cnt] of scores) {
      const pct = (cnt / stats.total * 100).toFixed(1);
      const barW = (cnt / maxScore * 100).toFixed(0);
      scoreHTML += `<div class="score-row">
        <span class="score-label">${sc}</span>
        <div class="score-bar-wrap"><div class="score-bar" style="width:${barW}%"></div></div>
        <span class="score-count">${cnt}次 (${pct}%)</span>
      </div>`;
    }
    $('scoreDist').innerHTML = scoreHTML;
    
  } catch (e) {
    console.error('加载总览失败:', e);
  }
}

// =============================================
// TAB 2: 预测
// =============================================
async function loadHistory() {
  try {
    const history = await api('/api/history');
    if (history.length === 0) {
      $('historyList').innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:20px;">暂无预测记录</div>';
      return;
    }
    const html = history.map(h => {
      const time = new Date(h.timestamp);
      const timeStr = `${time.getHours().toString().padStart(2,'0')}:${time.getMinutes().toString().padStart(2,'0')}`;
      return `<div class="history-item">
        <span class="history-time">${timeStr}</span>
        <span class="history-teams">${h.home} vs ${h.away}</span>
        <span class="history-result">${h.result.topScore} (${h.result.topPct}%)</span>
        <span style="color:var(--text-secondary);font-size:0.75rem;">λ ${h.lambda.home.toFixed(2)}:${h.lambda.away.toFixed(2)}</span>
      </div>`;
    }).join('');
    $('historyList').innerHTML = html;
  } catch (e) {
    console.error('加载历史失败:', e);
  }
}

async function predictAll() {
  $('predStatus').textContent = '🔄 计算中...';
  $('predictResults').innerHTML = '<div class="loading"><div class="spinner"></div><div>模拟 5000次/场...</div></div>';
  try {
    const data = await api('/api/predict/all', { method: 'POST' });
    const html = data.results.map(m => {
      const sim = m.fusion;
      const top = sim.top5[0];
      const hP = sim.homeWinPct.toFixed(1);
      const dP = sim.drawPct.toFixed(1);
      const aP = sim.awayWinPct.toFixed(1);
      return `<div class="pred-card">
        <div class="pred-date">${formatDate(m.date)} | Group ${m.group}</div>
        <div class="pred-teams">${m.home} vs ${m.away}</div>
        <div class="pred-lambda">融合λ ${m.fusion.lambda.home.toFixed(2)} : ${m.fusion.lambda.away.toFixed(2)}</div>
        <div class="pred-top">最可能: <strong>${top.score}</strong> (${top.pct}%)</div>
        <div class="win-bar-wrap">
          <div class="win-bar home-bar" style="width:${Math.round(sim.homeWinPct)}%">${m.home} ${hP}%</div>
          <div class="win-bar draw-bar" style="width:${Math.max(Math.round(sim.drawPct), 5)}%">平 ${dP}%</div>
          <div class="win-bar away-bar" style="width:${Math.round(sim.awayWinPct)}%">${m.away} ${aP}%</div>
        </div>
        <div class="pred-scores">
          ${sim.top5.slice(0, 3).map((s, i) => `<span class="score-chip ${i===0?'top':''}">${s.score} ${s.pct}%</span>`).join('')}
        </div>
      </div>`;
    }).join('');
    $('predictResults').innerHTML = html;
    $('predStatus').textContent = `✅ ${data.results.length} 场预测完成`;
    await loadHistory();
  } catch (e) {
    $('predStatus').textContent = `❌ 错误: ${e.message}`;
  }
}

// 自定义预测弹窗
function predictCustom() {
  $('customPredModal').style.display = 'flex';
  $('customPredResult').innerHTML = '';
}

function closeCustomPred() {
  $('customPredModal').style.display = 'none';
}

async function doCustomPredict() {
  const home = $('predHome').value;
  const away = $('predAway').value;
  if (!home || !away) { showToast('请选择主客队', 'error'); return; }
  if (home === away) { showToast('主客队不能相同', 'error'); return; }
  
  const oddsHome = parseFloat($('oddsHome').value) || null;
  const oddsDraw = parseFloat($('oddsDraw').value) || null;
  const oddsAway = parseFloat($('oddsAway').value) || null;
  const handicap = parseFloat($('handicap').value) || null;
  // 用户输入: -2=主队让2球(引擎handicap=2), +1=主队受让1球(引擎handicap=-1)
  const engineHandicap = handicap ? -handicap : null;
  const useAI = $('predUseAI').checked;
  
  $('customPredResult').innerHTML = '<div class="loading"><div class="spinner"></div><div>'+(useAI?'数学模型计算中...':'计算中...')+'</div></div>';
  try {
    const data = await api('/api/predict/match', {
      method: 'POST',
      body: {
        home, away,
        oddsHome, oddsDraw, oddsAway, handicap: engineHandicap,
        isFinalRound: $('predFinalRound').checked,
        isKnockout: $('predKnockout').checked,
        useAI
      }
    });
    
    if (data.error) { $('customPredResult').innerHTML = `<div style="color:var(--accent-red);padding:12px;">❌ ${data.error}</div>`; return; }
    
    const fusion = data.fusion;
    const top = fusion.top5[0];
    const models = data.models;
    const weights = data.weights;
    
    // ===== 生成完整的居中滑动卡片 =====
    let oddsInfo = '';
    if (models.market && !models.market.isInferred) {
      oddsInfo = `<div style="display:flex;justify-content:space-between;gap:8px;margin-top:10px;">
        ${['主胜','平局','客胜'].map((label, i) => {
          const o = [models.market.odds.home, models.market.odds.draw, models.market.odds.away][i];
          const p = [models.market.winPct, models.market.drawPct, models.market.awayPct][i];
          return `<div style="flex:1;background:var(--bg-hover);border-radius:8px;padding:8px;text-align:center;">
            <div style="font-size:0.7rem;color:var(--text-muted);">${label}</div>
            <div style="font-size:1.1rem;font-weight:700;color:var(--accent-orange);">${o}</div>
            <div style="font-size:0.75rem;color:var(--text-secondary);">${p}%</div>
          </div>`;
        }).join('')}
      </div>`;
      if (models.market.handicap) {
        // 引擎 handciop>0=主让, 显示转回用户语义: 用户输入-2=主队让2球
        const h = models.market.handicap;
        const displayH = -h;
        oddsInfo += `<div style="margin-top:6px;text-align:center;font-size:0.75rem;color:var(--text-muted);">⚖️ 让球盘口: ${displayH > 0 ? '+' : ''}${displayH} (主${displayH < 0 ? '让' : '受让'}${Math.abs(displayH)})</div>`;
      }
    }
    
    // 概率对比条（各模型 vs 融合）
    const modelBar = (label, hP, dP, aP, color) => `
      <div style="margin:6px 0;">
        <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:var(--text-muted);margin-bottom:2px;">
          <span>${label}</span>
          <span>${hP}% / ${dP}% / ${aP}%</span>
        </div>
        <div class="win-bar-wrap" style="height:14px;">
          <div class="win-bar" style="width:${Math.round(hP)}%;background:${color};">${hP}%</div>
          <div class="win-bar" style="width:${Math.max(Math.round(dP), 3)}%;background:${color}88;">${dP}%</div>
          <div class="win-bar" style="width:${Math.round(aP)}%;background:${color}44;">${aP}%</div>
        </div>
      </div>`;
    
    let modelHtml = `
    <div class="pred-modal-overlay" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:300;display:flex;align-items:center;justify-content:center;" onclick="if(event.target===this)this.style.display='none'">
      <div class="pred-scroll-card" style="background:var(--bg-primary);border:1px solid var(--border);border-radius:16px;max-width:680px;width:92%;max-height:85vh;overflow-y:auto;padding:0;box-shadow:0 8px 40px rgba(0,0,0,0.5);" onclick="event.stopPropagation()">
        
        <!-- 头部 VS -->
        <div style="background:linear-gradient(135deg,#1a2338,#0f1a2e);padding:20px;border-radius:16px 16px 0 0;text-align:center;border-bottom:1px solid var(--border);">
          <div style="display:flex;align-items:center;justify-content:center;gap:16px;">
            <div style="text-align:right;">
              <div style="font-size:1.3rem;font-weight:700;color:var(--accent-blue);">${home}</div>
              <div style="font-size:0.7rem;color:var(--text-muted);">Elo ${models.elo.rating.home}</div>
            </div>
            <div style="font-size:1.6rem;font-weight:900;background:var(--gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">VS</div>
            <div style="text-align:left;">
              <div style="font-size:1.3rem;font-weight:700;color:var(--accent-red);">${away}</div>
              <div style="font-size:0.7rem;color:var(--text-muted);">Elo ${models.elo.rating.away}</div>
            </div>
          </div>
          <div style="margin-top:8px;display:flex;justify-content:center;gap:20px;">
            <div class="live-badge">${models.market ? (models.market.isInferred ? '📊 Elo隐含' : '📊 含赔率') : '📊 无赔率'}</div>
            <div style="color:var(--text-muted);font-size:0.7rem;padding-top:3px;">🧮 DC ρ=${models.poisson.dcRho}</div>
          </div>
        </div>
        
        <!-- 胜率条 -->
        <div style="padding:16px 20px 0;">
          <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:var(--text-secondary);margin-bottom:4px;">
            <span>🏠 ${home}</span>
            <span>🤝 平局</span>
            <span>✈️ ${away}</span>
          </div>
          <div class="win-bar-wrap" style="height:28px;">
            <div class="win-bar home-bar" style="width:${Math.round(fusion.winPct)}%;font-size:0.75rem;">${fusion.winPct}%</div>
            <div class="win-bar draw-bar" style="width:${Math.max(Math.round(fusion.drawPct), 6)}%;font-size:0.7rem;">${fusion.drawPct}%</div>
            <div class="win-bar away-bar" style="width:${Math.round(fusion.awayPct)}%;font-size:0.75rem;">${fusion.awayPct}%</div>
          </div>
        </div>
        
        <!-- 比分分布 -->
        <div style="padding:14px 20px 0;">
          <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:8px;">🎯 最可能比分</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            ${fusion.top5.map((s, i) => {
              const maxPct = fusion.top5[0].pct;
              const barH = Math.round((s.pct / maxPct) * 100);
              return `<div style="flex:1;min-width:60px;background:var(--bg-hover);border-radius:8px;padding:6px;text-align:center;border:${i===0?'1px solid var(--accent-orange)':'1px solid var(--border)'};">
                <div style="font-size:1.1rem;font-weight:700;color:${i===0?'var(--accent-orange)':'var(--text-primary)'};">${s.score}</div>
                <div style="margin-top:4px;height:40px;background:var(--border);border-radius:4px;overflow:hidden;display:flex;align-items:flex-end;">
                  <div style="width:100%;height:${barH}%;background:${i===0?'var(--accent-orange)':'var(--accent-blue)'};border-radius:4px;transition:height 0.5s;"></div>
                </div>
                <div style="font-size:0.7rem;color:var(--text-secondary);margin-top:2px;">${s.pct}%</div>
              </div>`;
            }).join('')}
          </div>
        </div>
        
        <!-- 模型对比 -->
        <div style="padding:14px 20px 0;">
          <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:6px;">🔬 各模型胜率对比</div>
          ${modelBar('⚡ Elo', models.elo.winPct, models.elo.drawPct, models.elo.awayPct, '#3b82f6')}
          ${modelBar('📊 泊松', models.poisson.winPct, models.poisson.drawPct, models.poisson.awayPct, '#8b5cf6')}
          ${modelBar('💰 经济', models.economic.winPct, models.economic.drawPct, models.economic.awayPct, '#22c55e')}
          ${models.market ? modelBar('🎯 市场', models.market.winPct, models.market.drawPct, models.market.awayPct, '#f59e0b') : ''}
          <div style="margin-top:6px;border-top:1px solid var(--border);padding-top:6px;">
            ${modelBar('🏆 融合', fusion.winPct, fusion.drawPct, fusion.awayPct, '#ef4444')}
          </div>
        </div>
        
        <!-- 赔率信息 -->
        ${oddsInfo ? `<div style="padding:14px 20px 0;">${oddsInfo}</div>` : ''}
        
        <!-- 融合 λ -->
        <div style="padding:14px 20px;">
          <div style="display:flex;justify-content:center;gap:24px;background:var(--bg-hover);border-radius:10px;padding:10px;">
            <div style="text-align:center;">
              <div style="font-size:0.65rem;color:var(--text-muted);">📈 融合λ</div>
              <div style="font-size:1.2rem;font-weight:700;color:var(--accent-blue);">${fusion.lambda.home.toFixed(2)}</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:0.65rem;color:var(--text-muted);">⚖️ 权重分配</div>
              <div style="font-size:0.75rem;color:var(--text-secondary);">${weights.elo*100}%/${weights.poisson*100}%/${weights.economic*100}%/${weights.market*100}%</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:0.65rem;color:var(--text-muted);">📉 融合λ</div>
              <div style="font-size:1.2rem;font-weight:700;color:var(--accent-red);">${fusion.lambda.away.toFixed(2)}</div>
            </div>
          </div>
        </div>`;
    
    // AI 推理报告
    if (data.aiReport && data.aiReport.report) {
      const report = data.aiReport.report;
      // 解析报告中的表格
      const tableMatch = report.match(/\|.*?\|.*?\|.*?\|.*?\|/g);
      const conclusionMatch = report.match(/## 四、最终结论[\s\S]*?(?=\n##|$)/);
      
      modelHtml += `<div style="padding:0 20px 16px;">
        <div style="background:var(--bg-secondary);border:1px solid var(--accent-purple);border-radius:12px;overflow:hidden;">
          <div style="background:var(--accent-purple);padding:8px 14px;display:flex;align-items:center;gap:8px;">
            <span style="font-size:1rem;">🧠</span>
            <span style="font-weight:600;font-size:0.85rem;color:#fff;">AI 推理裁判</span>
            <span style="font-size:0.7rem;color:rgba(255,255,255,0.7);">deepseek-v4-flash</span>
          </div>
          <div style="padding:12px 14px;font-size:0.82rem;line-height:1.7;">
            ${report.split('\n').filter(l => l.trim()).map(line => {
              if (line.startsWith('## ')) return `<h4 style="margin:12px 0 6px;color:var(--accent-orange);font-size:0.9rem;">${line.replace(/^##\s*/, '')}</h4>`;
              if (line.startsWith('| ')) {
                const cells = line.split('|').filter(c => c.trim());
                if (cells.length >= 4 && cells[0].includes('排名')) return `<div style="display:grid;grid-template-columns:50px 1fr 80px 1fr;gap:4px;font-weight:600;color:var(--text-secondary);font-size:0.75rem;margin:8px 0 4px;padding:0 4px;">${cells.map(c => `<div>${c.trim()}</div>`).join('')}</div>`;
                if (cells.length >= 4) {
                  const isTop1 = cells[0].trim() === '1';
                  return `<div style="display:grid;grid-template-columns:50px 1fr 80px 1fr;gap:4px;font-size:0.78rem;margin:3px 0;padding:4px;border-radius:6px;${isTop1?'background:var(--bg-hover);border:1px solid var(--accent-orange)':'background:var(--bg-hover)'}">
                    ${cells.map((c, i) => `<div style="${i===0?'font-weight:700;color:var(--accent-orange)':i===1?'font-weight:700':i===3?'color:var(--text-muted);font-size:0.72rem':''}">${c.trim()}</div>`).join('')}
                  </div>`;
                }
                return `<div style="color:var(--text-secondary);padding:2px 0;">${line}</div>`;
              }
              if (line.startsWith('- **')) {
                const bold = line.match(/- \*\*(.*?)\*\*：(.*)/);
                if (bold) return `<div style="margin:3px 0;padding-left:8px;"><strong style="color:var(--accent-blue);">${bold[1]}</strong>：${bold[2]}</div>`;
              }
              return `<div style="padding:1px 0;">${line}</div>`;
            }).join('')}
          </div>
        </div>
      </div>`;
    } else if (data.aiReport && data.aiReport.error) {
      modelHtml += `<div style="padding:0 20px 16px;"><div style="padding:12px;background:var(--bg-secondary);border:1px solid var(--accent-red);border-radius:10px;font-size:0.8rem;color:var(--accent-red);">❌ AI推理暂不可用: ${data.aiReport.error}</div></div>`;
    }
    
    // 关闭按钮
    modelHtml += `<div style="padding:0 20px 16px;text-align:center;">
      <button class="btn btn-outline" onclick="this.closest('.pred-modal-overlay').style.display='none'" style="width:100%;">✕ 关闭</button>
    </div>`;
    
    modelHtml += `</div></div>`;
    
    $('customPredResult').innerHTML = modelHtml;
    await loadHistory();
  } catch (e) {
    $('customPredResult').innerHTML = `<div style="color:var(--accent-red);padding:12px;">❌ ${e.message}</div>`;
  }
}

// =============================================
// TAB 3: 出线形势
// =============================================
async function runAdvanceSim() {
  $('advanceStatus').textContent = '🔄 模拟 10000次...';
  loading($('advanceTableWrap'), '模拟出线形势中...');
  try {
    const data = await api('/api/predict/advance', { method: 'POST', body: { simulations: 10000 } });
    
    // 按小组排列
    const groupOrder = ['A','B','C','D','E','F','G','H','I','J','K','L'];
    let html = '<table class="advance-table"><thead><tr><th>小组</th><th>球队</th><th>出线率</th><th>小组第1</th><th>小组第2</th><th>最佳第3</th><th>8强</th><th>4强</th><th>亚军</th><th>冠军</th></tr></thead><tbody>';
    
    for (const g of groupOrder) {
      const teams = data.group[g];
      const sorted = teams.map(t => ({ name: t, ...data.results[t] })).sort((a, b) => b.advancePct - a.advancePct);
      for (const t of sorted) {
        const barClass = t.advancePct >= 70 ? 'progress-high' : t.advancePct >= 30 ? 'progress-mid' : t.advancePct >= 10 ? 'progress-low' : 'progress-none';
        html += `<tr>
          <td>${g}</td>
          <td style="font-weight:600;">${t.name}</td>
          <td><div class="progress-bar-wrap"><div class="progress-bar ${barClass}" style="width:${t.advancePct}%">${t.advancePct}%</div></div></td>
          <td>${t.groupWinPct}%</td>
          <td>${t.groupRunnerUpPct}%</td>
          <td>${t.bestThirdPct}%</td>
          <td>${t.round8Pct}%</td>
          <td>${t.round4Pct}%</td>
          <td>${t.runnerUpPct}%</td>
          <td style="font-weight:700;color:var(--accent-orange);">${t.championPct}%</td>
        </tr>`;
      }
    }
    html += '</tbody></table>';
    $('advanceTableWrap').innerHTML = html;
    $('advanceStatus').textContent = `✅ ${data.totalSims.toLocaleString()} 次模拟完成`;
  } catch (e) {
    $('advanceStatus').textContent = `❌ 错误: ${e.message}`;
    $('advanceTableWrap').innerHTML = `<div style="color:var(--accent-red);text-align:center;padding:20px;">${e.message}</div>`;
  }
}

// =============================================
// TAB 4: 球队数据编辑
// =============================================
let allTeams = [];

async function loadTeamEdit() {
  allTeams = await api('/api/teams');
  renderTeamEdit();
}

function renderTeamEdit() {
  const filter = $('teamGroupFilter').value;
  const search = $('teamSearch').value.toLowerCase();
  
  let filtered = allTeams;
  if (filter) filtered = filtered.filter(t => t.group === filter);
  if (search) filtered = filtered.filter(t => t.name.includes(search));
  
  const fields = [
    { key: 'attackBase', label: '进攻', min: 0.1, max: 3.0, step: 0.1 },
    { key: 'defenseBase', label: '防守', min: 0.1, max: 3.0, step: 0.1 },
    { key: 'styleFactor', label: '风格因子', min: 0.5, max: 1.5, step: 0.05 },
    { key: 'rank', label: 'FIFA排名', min: 1, max: 100, step: 1 },
    { key: 'eloRating', label: 'ELO评分', min: 1000, max: 2500, step: 1 },
  ];
  
  const html = filtered.map(t => {
    const fieldInputs = fields.map(f => `
      <div class="team-field">
        <span class="field-label">${f.label}</span>
        <input class="team-edit-input" type="number" min="${f.min}" max="${f.max}" step="${f.step}" 
               value="${t[f.key] ?? ''}" data-team="${t.name}" data-field="${f.key}">
      </div>
    `).join('');
    
    return `<div class="team-card">
      <div class="team-card-header">
        <h4>${t.name}</h4>
        <span class="group-tag">${t.group}</span>
      </div>
      <div style="margin-bottom:6px;">
        <span class="field-label">风格: </span>
        <select class="team-edit-select" data-team="${t.name}" data-field="style">
          ${['控球渗透','全能攻防','个人突破','快速转换','高压控球','传控','边路进攻',
            '全攻全守','中场控制','强硬防守','中场绞杀','体能压制','防守反击',
            '技术流派','快速反击','团队配合','身体对抗','防守稳固','长传冲吊',
            '速度突破','身体+速度','高压逼抢','情绪化进攻','铁桶防守','技术不足']
            .map(s => `<option value="${s}" ${t.style===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>
      <div style="margin-bottom:6px;">
        <span class="field-label">控球: </span>
        <select class="team-edit-select" data-team="${t.name}" data-field="possessionStyle">
          <option value="low" ${t.possessionStyle==='low'?'selected':''}>低</option>
          <option value="medium" ${!t.possessionStyle || t.possessionStyle==='medium'?'selected':''}>中</option>
          <option value="high" ${t.possessionStyle==='high'?'selected':''}>高</option>
        </select>
      </div>
      ${fieldInputs}
      <button class="team-save-btn" onclick="saveTeam('${t.name}')">💾 保存</button>
    </div>`;
  }).join('');
  
  $('teamEditGrid').innerHTML = html || '<div style="color:var(--text-muted);text-align:center;padding:40px;">没有匹配的球队</div>';
}

async function saveTeam(name) {
  const inputs = document.querySelectorAll(`[data-team="${name}"]`);
  const body = {};
  for (const inp of inputs) {
    const field = inp.dataset.field;
    let val = inp.value;
    if (inp.type === 'number') val = parseFloat(val);
    if (!isNaN(val) && val !== '') body[field] = val;
    else if (field === 'style' || field === 'possessionStyle') body[field] = val;
  }
  
  try {
    await api(`/api/teams/${encodeURIComponent(name)}`, { method: 'PUT', body });
    showToast(`✅ ${name} 已保存`, 'success');
  } catch (e) {
    showToast(`❌ 保存失败: ${e.message}`, 'error');
  }
}

// =============================================
// TAB 5: 比赛管理
// =============================================
async function loadMatchList() {
  try {
    const matches = await api('/api/matches/completed');
    // 按日期倒序
    const sorted = [...matches].reverse();
    const html = sorted.map((m, i) => {
      const idx = matches.length - 1 - i;
      return `<div class="match-item">
        <span class="match-date">${m.date}</span>
        <span class="match-group">${m.group}</span>
        <span class="match-teams">${m.home} vs ${m.away}</span>
        <span class="match-score">${m.score}</span>
        <button class="match-delete" onclick="deleteMatch(${idx})" title="删除">✕</button>
      </div>`;
    }).join('');
    $('matchList').innerHTML = html || '<div style="color:var(--text-muted);text-align:center;padding:20px;">暂无比赛记录</div>';
  } catch (e) {
    console.error('加载比赛失败:', e);
  }
}

async function addMatchResult() {
  const date = $('matchDate').value;
  const group = $('matchGroup').value;
  const home = $('matchHome').value;
  const away = $('matchAway').value;
  const score = $('matchScore').value;
  const round = parseInt($('matchRound').value) || 3;
  
  if (!home || !away || !score) { showToast('请填写完整信息', 'error'); return; }
  if (!/^\d+-\d+$/.test(score)) { showToast('比分格式: x-y', 'error'); return; }
  
  try {
    await api('/api/matches/result', {
      method: 'POST',
      body: { date, group, home, away, score, round }
    });
    showToast(`✅ ${home} ${score} ${away} 已添加`, 'success');
    $('matchScore').value = '';
    await Promise.all([loadMatchList(), loadOverview()]);
  } catch (e) {
    showToast(`❌ ${e.message}`, 'error');
  }
}

async function deleteMatch(idx) {
  if (!confirm('确认删除该比赛结果？')) return;
  try {
    await api(`/api/matches/${idx}`, { method: 'DELETE' });
    showToast('✅ 已删除', 'success');
    await Promise.all([loadMatchList(), loadOverview()]);
  } catch (e) {
    showToast(`❌ ${e.message}`, 'error');
  }
}

// =============================================
// TAB 6: 模型配置
// =============================================
let currentConfig = {};

async function loadConfig() {
  try {
    currentConfig = await api('/api/config');
    const weights = currentConfig.fusionWeights || { elo: 0.25, poisson: 0.30, economic: 0.10, market: 0.35 };
    const fields = [
      { key: 'monteCarloRuns', label: '蒙特卡洛模拟次数', min: 1000, max: 50000, step: 1000 },
      { key: 'homeAdvantage', label: '主场优势系数', min: 0.9, max: 1.3, step: 0.01 },
      { key: 'dcRho', label: 'Dixon-Coles ρ', min: 0, max: 0.5, step: 0.01 },
      { key: 'realPerformanceWeight', label: '实际表现权重', min: 0, max: 1, step: 0.05 },
      { key: 'preseasonWeight', label: '赛前预测权重', min: 0, max: 1, step: 0.05 },
      { key: 'finalRoundFactor', label: '末轮保守因子', min: 0.7, max: 1, step: 0.01 },
    ];
    
    const weightFields = [
      { key: 'elo', label: 'Elo 权重', min: 0, max: 1, step: 0.05 },
      { key: 'poisson', label: '泊松权重', min: 0, max: 1, step: 0.05 },
      { key: 'economic', label: '经济学权重', min: 0, max: 1, step: 0.05 },
      { key: 'market', label: '市场赔率权重', min: 0, max: 1, step: 0.05 },
    ];
    
    let html = '<h3 style="margin-bottom:10px;font-size:0.95rem;color:var(--text-secondary);">基础参数</h3>';
    html += fields.map(f => `
      <div class="config-item">
        <label>${f.label}</label>
        <input type="number" id="cfg-${f.key}" value="${currentConfig[f.key] || ''}" 
               min="${f.min}" max="${f.max}" step="${f.step}">
      </div>
    `).join('');
    
    html += '<h3 style="margin:16px 0 10px;font-size:0.95rem;color:var(--text-secondary);">融合模型权重 (总和=1)</h3>';
    html += weightFields.map(f => `
      <div class="config-item">
        <label>${f.label}</label>
        <input type="number" id="fw-${f.key}" value="${weights[f.key] || 0}" 
               min="${f.min}" max="${f.max}" step="${f.step}">
      </div>
    `).join('');
    
    $('configGrid').innerHTML = html;
    
  } catch (e) {
    console.error('加载配置失败:', e);
  }
}

async function saveConfig() {
  const fields = ['monteCarloRuns', 'homeAdvantage', 'dcRho', 'realPerformanceWeight', 'preseasonWeight', 'finalRoundFactor'];
  const body = {};
  for (const f of fields) {
    body[f] = parseFloat($(`cfg-${f}`).value);
  }
  // 融合权重
  const weightKeys = ['elo', 'poisson', 'economic', 'market'];
  const fw = {};
  for (const k of weightKeys) {
    fw[k] = parseFloat($(`fw-${k}`).value) || 0;
  }
  body.fusionWeights = fw;
  
  try {
    const result = await api('/api/config', { method: 'PUT', body });
    currentConfig = result.config;
    showToast('✅ 配置已保存', 'success');
  } catch (e) {
    showToast(`❌ ${e.message}`, 'error');
  }
}

async function runAnalysis() {
  $('analysisResult').innerHTML = '<div class="loading"><div class="spinner"></div><div>分析中...</div></div>';
  try {
    const data = await api('/api/analyze');
    $('analysisResult').innerHTML = `
      <div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px;">
        <h3 style="margin-bottom:10px;">📊 模型准确率 (泊松基准)</h3>
        <div style="display:flex;gap:20px;flex-wrap:wrap;">
          <div class="stat-card" style="flex:1;"><span class="num">${data.resultAccuracy}%</span><span class="label">结果方向准确率</span></div>
          <div class="stat-card" style="flex:1;"><span class="num">${data.exactScore}%</span><span class="label">精确比分准确率</span></div>
          <div class="stat-card" style="flex:1;"><span class="num">${data.testSize}</span><span class="label">验证场次</span></div>
        </div>
        <p style="margin-top:10px;color:var(--text-secondary);font-size:0.8rem;">注: 融合模型准确率需积累赔率数据后评估</p>
      </div>`;
  } catch (e) {
    $('analysisResult').innerHTML = `<div style="color:var(--accent-red);padding:12px;">❌ ${e.message}</div>`;
  }
}

// TAB 6: 复盘分析
// =============================================
async function loadReview() {
  try {
    const data = await api('/api/review');
    if (!data.total) {
      $('reviewContainer').innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">暂无比赛数据</div>';
      return;
    }
    
    let html = '';
    
    // 概览卡片
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin-bottom:14px;">';
    const cards = [
      { label: '总场次', val: data.total, cls: '' },
      { label: '方向正确', val: data.correct+'/'+data.total+' ('+data.correctPct+'%)', cls: data.correctPct >= 65 ? 'color:var(--accent-green)' : 'color:var(--accent-orange)' },
      { label: '有赔率', val: data.withOdds.correct+'/'+data.withOdds.count, sub: data.withOdds.count > 0 ? '('+(data.withOdds.correct/data.withOdds.count*100).toFixed(0)+'%)' : '', cls: '' },
      { label: '无赔率', val: data.noOdds.correct+'/'+data.noOdds.count, sub: data.noOdds.count > 0 ? '('+(data.noOdds.correct/data.noOdds.count*100).toFixed(0)+'%)' : '', cls: '' },
      { label: '精确命中', val: data.exact.length+'/'+data.total, sub: '('+(data.exact.length/data.total*100).toFixed(1)+'%)', cls: 'color:var(--accent-blue)' },
      { label: '错判', val: data.wrong.length, sub: '('+(data.wrong.length/data.total*100).toFixed(0)+'%)', cls: 'color:var(--accent-red)' },
    ];
    for (const c of cards) {
      html += '<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:10px;text-align:center;">';
      html += '<div style="font-size:0.65rem;color:var(--text-muted);margin-bottom:2px;">'+c.label+'</div>';
      html += '<div style="font-size:1.2rem;font-weight:700;'+(c.cls||'')+'">'+c.val+'</div>';
      if (c.sub) html += '<div style="font-size:0.7rem;color:var(--text-secondary);">'+c.sub+'</div>';
      html += '</div>';
    }
    html += '</div>';
    
    // 比分偏差
    html += '<div style="margin-bottom:14px;">';
    html += '<h3 style="font-size:0.9rem;margin-bottom:6px;color:var(--text-primary);">📊 比分偏差分布</h3>';
    html += '<div style="display:flex;gap:6px;">';
    for (const [k,v] of Object.entries(data.scoreBins)) {
      const pct = (v/data.total*100).toFixed(0);
      html += '<div style="flex:1;background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:8px;text-align:center;">';
      html += '<div style="font-size:0.7rem;color:var(--text-muted);">'+k+'</div>';
      html += '<div style="font-size:1rem;font-weight:700;">'+v+'</div>';
      html += '<div style="font-size:0.7rem;color:var(--text-secondary);">'+pct+'%</div></div>';
    }
    html += '</div></div>';
    
    // 小组准确率
    html += '<div style="margin-bottom:14px;">';
    html += '<h3 style="font-size:0.9rem;margin-bottom:6px;color:var(--text-primary);">📋 各小组方向正确率</h3>';
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;">';
    for (const [g, s] of Object.entries(data.groupStats).sort()) {
      const pct = (s.c/s.t*100).toFixed(0);
      const barCls = pct >= 75 ? 'progress-high' : pct >= 50 ? 'progress-mid' : 'progress-low';
      html += '<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;padding:6px 10px;display:flex;justify-content:space-between;align-items:center;">';
      html += '<span style="font-weight:600;font-size:0.85rem;">'+g+'组</span>';
      html += '<div style="flex:1;margin:0 8px;"><div class="progress-bar-wrap" style="height:10px;"><div class="progress-bar '+barCls+'" style="width:'+pct+'%"></div></div></div>';
      html += '<span style="font-size:0.8rem;font-family:var(--font-mono);">'+s.c+'/'+s.t+' ('+pct+'%)</span></div>';
    }
    html += '</div></div>';
    
    // 错判比赛
    html += '<h3 style="font-size:0.9rem;margin-bottom:6px;color:var(--accent-red);">❌ 方向错误 ('+data.wrong.length+'场)</h3>';
    for (const r of data.wrong) {
      const emoji = r.actualResult === 'home' ? '🏠' : r.actualResult === 'draw' ? '🤝' : '✈️';
      const dirStr = r.actualResult === 'home' ? '主胜' : r.actualResult === 'draw' ? '平局' : '客胜';
      html += '<div style="background:var(--bg-secondary);border:1px solid var(--accent-red);border-left:3px solid var(--accent-red);border-radius:8px;padding:8px 12px;margin-bottom:6px;">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px;">';
      html += '<span style="font-weight:600;font-size:0.85rem;">'+flag(r.home)+' '+r.home+' '+r.score+' '+flag(r.away)+' '+r.away+'</span>';
      html += '<span style="font-size:0.75rem;background:var(--accent-red);color:#fff;padding:1px 6px;border-radius:4px;">实际 '+emoji+' '+dirStr+'</span></div>';
      html += '<div style="margin-top:4px;display:flex;gap:12px;font-size:0.75rem;color:var(--text-secondary);flex-wrap:wrap;">';
      html += '<span>模型: <b>'+r.homePct+'%</b> / '+r.drawPct+'% / '+r.awayPct+'%</span>';
      html += '<span>Top1: '+r.predTop1+' ('+r.top1Pct+'%)</span>';
      html += '<span>λ '+r.lambdaH+' : '+r.lambdaA+'</span>';
      html += '<span>赔率: '+r.oddsStr+'</span>';
      html += '<span>让球: '+(r.handicap < 0 ? '主受让'+Math.abs(r.handicap) : '主让'+r.handicap)+'</span></div></div>';
    }
    
    // 精确命中
    html += '<h3 style="font-size:0.9rem;margin:12px 0 6px;color:var(--accent-green);">🎯 精确命中比分 ('+data.exact.length+'场)</h3>';
    html += '<div style="display:flex;flex-wrap:wrap;gap:6px;">';
    for (const r of data.exact) {
      html += '<div style="background:var(--bg-secondary);border:1px solid var(--accent-green);border-radius:6px;padding:6px 10px;font-size:0.78rem;">✅ '+flag(r.home)+' '+r.home+' '+r.score+' '+flag(r.away)+' '+r.away+'</div>';
    }
    html += '</div>';
    
    // 改进建议
    html += '<div style="margin-top:14px;background:var(--bg-secondary);border:1px solid var(--accent-blue);border-radius:8px;padding:10px 14px;">';
    html += '<div style="font-size:0.85rem;font-weight:600;margin-bottom:4px;color:var(--accent-blue);">💡 改进建议</div>';
    html += '<div style="font-size:0.78rem;color:var(--text-secondary);line-height:1.6;">';
    html += '• 方向正确率 <b>'+data.correctPct+'%</b> — 整体可接受，平局预测偏保守<br>';
    html += '• 错判 <b>'+data.wrong.length+'</b> 场中大部分是预测主胜但实际打平<br>';
    html += '• 让球盘口方向正确率表现良好，赔率数据帮助明显<br>';
    html += '• 第3轮预测可参考复盘结果，注意末轮战意影响</div></div>';
    
    $('reviewContainer').innerHTML = html;
  } catch (e) {
    $('reviewContainer').innerHTML = '<div style="color:var(--accent-red);text-align:center;padding:40px;">❌ '+e.message+'</div>';
  }
}

// =============================================
// TAB 7: Elo 排名
// =============================================
async function loadEloRanking() {
  try {
    const eloList = await api('/api/elo');
    let html = '<table class="advance-table"><thead><tr><th>排名</th><th>球队</th><th>小组</th><th>Elo 等级分</th><th>FIFA排名</th><th>实力条</th></tr></thead><tbody>';
    eloList.forEach((t, i) => {
      const rankClass = i < 4 ? 'rank-1' : i < 8 ? 'rank-2' : '';
      const maxElo = Math.max(...eloList.map(x => x.elo));
      const barPct = (t.elo / maxElo * 100).toFixed(0);
      const barColor = i < 4 ? 'progress-high' : i < 12 ? 'progress-mid' : i < 24 ? 'progress-low' : 'progress-none';
      html += `<tr>
        <td style="font-weight:700;">${i + 1}</td>
        <td class="${rankClass}" style="font-weight:600;">${t.name}</td>
        <td>${t.group}</td>
        <td style="font-weight:700;font-family:var(--font-mono);">${t.elo}</td>
        <td>${t.rank || '-'}</td>
        <td><div class="progress-bar-wrap"><div class="progress-bar ${barColor}" style="width:${barPct}%">${t.elo}</div></div></td>
      </tr>`;
    });
    html += '</tbody></table>';
    $('eloTableWrap').innerHTML = html;
  } catch (e) {
    $('eloTableWrap').innerHTML = `<div style="color:var(--accent-red);text-align:center;padding:20px;">${e.message}</div>`;
  }
}

// =============================================
// TAB 7: 晋级图
// =============================================
async function loadKnockout() {
  try {
    const data = await api('/api/knockout');
    const tree = data.knockoutTree;
    const groupInfo = data.groupInfo;
    const allStandings = data.standings;
    
    if (!tree) {
      $('knockoutContainer').innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">暂无淘汰赛数据</div>';
      return;
    }
    
    let html = '';
    
    // 小组形势卡片
    html += '<div style="margin-bottom:16px;">';
    html += '<h3 style="font-size:0.95rem;margin-bottom:8px;color:var(--text-primary);">📋 小组末轮形势</h3>';
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px;">';
    for (const [g, info] of Object.entries(groupInfo)) {
      const desc = info.description || '';
      const rankHtml = (info.currentRanking || []).map((s, i) => {
        const r = i + 1;
        const rClass = r <= 2 ? 'rank-1' : '';
        return `<div style="display:flex;justify-content:space-between;padding:2px 6px;font-size:0.78rem;${r <= 2 ? 'font-weight:600;' : ''}">
          <span class="${rClass}">${flag(s.team)} ${s.team}</span>
          <span style="font-family:var(--font-mono);">${s.p}分 (${s.w}胜${s.d}平${s.l}负)</span>
        </div>`;
      }).join('');
      html += `<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:8px;">
        <div style="font-weight:700;font-size:0.85rem;margin-bottom:4px;color:var(--accent-blue);">Group ${g}</div>
        ${rankHtml}
        <div style="margin-top:4px;font-size:0.7rem;color:var(--text-secondary);padding-left:6px;">${desc}</div>
      </div>`;
    }
    html += '</div></div>';
    
    // 淘汰赛晋级图
    html += '<h3 style="font-size:0.95rem;margin:16px 0 8px;color:var(--text-primary);">🏆 淘汰赛对阵</h3>';
    
    const rounds = [
      { key: 'round64', label: '1/16 决赛 (32强)', color: '#2563eb' },
      { key: 'round16', label: '1/8 决赛 (16强)', color: '#7c3aed' },
      { key: 'round8', label: '1/4 决赛 (8强)', color: '#d97706' },
      { key: 'semi', label: '半决赛', color: '#dc2626' },
      { key: 'final', label: '决赛', color: '#16a34a' },
    ];
    
    for (const round of rounds) {
      const matches = tree[round.key];
      if (!matches || matches.length === 0) continue;
      
      html += `<div style="margin-bottom:12px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <div style="width:10px;height:10px;border-radius:50%;background:${round.color};"></div>
          <span style="font-weight:600;font-size:0.85rem;">${round.label}</span>
          <span style="font-size:0.7rem;color:var(--text-muted);">${matches.length}场</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:6px;">
          ${matches.map(m => {
            const hName = m.home.startsWith('T3') ? '小组第三' : m.home.startsWith('W') ? '待定' : m.home.startsWith('L') ? '待定' : m.home;
            const aName = m.away.startsWith('T3') ? '小组第三' : m.away.startsWith('W') ? '待定' : m.away.startsWith('L') ? '待定' : m.away;
            const hClass = m.home.startsWith('T3') || m.home.startsWith('W') || m.home.startsWith('L') ? 'color:var(--text-muted)' : 'color:var(--accent-blue);font-weight:600';
            const aClass = m.away.startsWith('T3') || m.away.startsWith('W') || m.away.startsWith('L') ? 'color:var(--text-muted)' : 'color:var(--accent-red);font-weight:600';
            return `<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:8px;padding:8px;font-size:0.8rem;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="${hClass}">${hName}</span>
                <span style="font-size:0.65rem;color:var(--text-muted);padding:0 6px;">vs</span>
                <span style="${aClass}">${aName}</span>
              </div>
              <div style="font-size:0.65rem;color:var(--text-muted);margin-top:3px;text-align:center;">📍 ${m.venue}</div>
            </div>`;
          }).join('')}
        </div>
      </div>`;
    }
    
    $('knockoutContainer').innerHTML = html;
  } catch (e) {
    $('knockoutContainer').innerHTML = `<div style="color:var(--accent-red);text-align:center;padding:20px;">${e.message}</div>`;
  }
}

// =============================================
// 启动
// =============================================
document.addEventListener('DOMContentLoaded', init);