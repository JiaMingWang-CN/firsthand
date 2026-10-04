<script setup>
// 演示用“截图”：用 HTML 绘制虚构产品「青檀表单」的页面。
// 它代表一张图片，因此使用自己固定的配色（不随主题变化），见交付说明。
import { computed } from 'vue'
const props = defineProps({
  screen: { type: String, default: 'landing' },
  device: { type: String, default: 'desktop' },
  target: { type: String, default: '' },
  path: { type: String, default: '/' },
  live: Boolean,
  time: { type: String, default: '21:10' },
})
const m = computed(() => props.device === 'mobile')
const hl = (k) => (props.target === k ? 'hl' : '')
const host = computed(() => (props.path.startsWith('mail.') ? '' : 'demo.qingtan.test'))
const urlText = computed(() => (host.value ? host.value + props.path : props.path))
const dark = computed(() => props.screen === 'dark-chart')
const wechat = computed(() => props.screen === 'wechat')
</script>

<template>
  <div class="shot" :class="{ m, dark, live }" role="img" :aria-label="`页面截图：${urlText}`">
    <!-- 浏览器外壳 -->
    <div v-if="!m" class="chrome">
      <span class="lights"><i></i><i></i><i></i></span>
      <span class="url"><span class="lock">⏺</span>{{ urlText }}</span>
    </div>
    <div v-else class="phone-top">
      <span class="num">{{ time }}</span><span class="notch"></span><span>5G ▮▮▮</span>
    </div>
    <div v-if="m && !wechat" class="m-url">{{ urlText }}</div>
    <div v-if="wechat" class="wx-bar"><span>✕</span><b>社团招新报名</b><span>⋯</span></div>

    <div class="vp">
      <!-- 顶栏（产品内页） -->
      <div v-if="!['landing','signup','signup-exists','mail','login','fill','wechat','pricing'].includes(screen)" class="appbar">
        <span class="brand"><i class="leaf"></i>青檀表单</span>
        <span v-if="!m" class="nav"><b>我的表单</b><span>模板</span><span>团队</span></span>
        <span class="sp"></span>
        <span class="up" v-if="!m">升级</span>
        <span class="me">林</span>
      </div>

      <!-- 营销首页 -->
      <template v-if="screen === 'landing'">
        <div class="mk-nav">
          <span class="brand"><i class="leaf"></i>青檀表单</span><span class="sp"></span>
          <span v-if="!m" class="lnk">模板</span><span v-if="!m" class="lnk">价格</span>
          <span class="lnk login" :class="hl('login')">登录</span>
        </div>
        <div class="hero">
          <div class="h1">三分钟搭一张表单<br v-if="m" />回复实时可见</div>
          <div class="p">模板即用 · 链接 / 二维码分享 · 一键导出</div>
          <div class="row-btn"><span class="b pri" :class="hl('signup')">免费注册</span><span class="b">看看模板</span></div>
          <div class="mock-form"><i></i><i></i><i class="s"></i><i></i></div>
        </div>
      </template>

      <!-- 登录 -->
      <template v-else-if="screen === 'login'">
        <div class="auth">
          <span class="brand c"><i class="leaf"></i>青檀表单</span>
          <div class="h2">登录</div>
          <div class="in">tester+free@qingtan.test</div><div class="in pw">••••••••••</div>
          <span class="b pri full">登录</span>
        </div>
      </template>

      <!-- 注册 -->
      <template v-else-if="screen === 'signup' || screen === 'signup-exists'">
        <div class="auth">
          <span class="brand c"><i class="leaf"></i>青檀表单</span>
          <div class="h2">创建账号</div>
          <div class="in" :class="{ err: screen === 'signup-exists' || target === 'error' }">{{ screen === 'signup-exists' ? 'chenmo.store@mail.qingtan.test' : 'tester@mail.qingtan.test' }}</div>
          <div v-if="screen === 'signup-exists'" class="errtxt" :class="hl('error')">该邮箱已注册，请直接登录或找回密码</div>
          <div v-else-if="target === 'error'" class="errtxt hl">请输入有效的邮箱地址，例如 name@company.com</div>
          <div class="in pw">••••••••••</div>
          <div class="hint">至少 8 位，包含字母和数字</div>
          <span class="b pri full" :class="hl('submit')">注册</span>
          <div class="fine">已有账号？<u>登录</u> · <u>忘记密码</u></div>
        </div>
      </template>

      <!-- 邮箱 -->
      <template v-else-if="screen === 'mail'">
        <div class="mail">
          <div class="mail-h">收件箱 <span>3</span></div>
          <div class="mail-row"><b>618 大促最后一天</b><span>营销</span></div>
          <div class="mail-row open">
            <b>请验证你的青檀表单邮箱</b>
            <div class="mail-body">你好，点击下方按钮完成邮箱验证。<span class="b pri" :class="hl('verify')">验证邮箱</span></div>
          </div>
          <div class="mail-row"><b>你的周报已生成</b><span>系统</span></div>
        </div>
      </template>

      <!-- 新手引导 -->
      <template v-else-if="screen === 'onboarding'">
        <div class="onb">
          <div class="stepper"><i class="on"></i><i class="on"></i><i :class="{ on: path.includes('step=3') }"></i><i></i></div>
          <div class="h2">{{ path.includes('step=3') ? '连接数据源（可选）' : '欢迎！先告诉我们你的用途' }}</div>
          <div class="opts"><span>活动报名</span><span>满意度调查</span><span>内部审批</span><span>其他</span></div>
          <div class="row-btn end"><span class="skip" :class="hl('skip')">跳过</span><span class="b pri">下一步</span></div>
        </div>
      </template>

      <!-- 表单列表 -->
      <template v-else-if="screen === 'dashboard'">
        <div class="pg">
          <div class="pg-h"><b>我的表单</b><span class="b pri sm" :class="hl('new')">＋ 新建表单</span></div>
          <div class="cards">
            <div class="fc"><b>门店周反馈</b><span>126 条回复 · 收集中</span></div>
            <div class="fc"><b>门店巡检反馈</b><span>2,318 条回复 · 收集中</span></div>
            <div class="fc dim" v-if="!m"><b>年会报名</b><span>已结束</span></div>
          </div>
        </div>
      </template>

      <!-- 模板库 -->
      <template v-else-if="screen === 'templates'">
        <div class="pg">
          <div class="pg-h"><b>模板库</b><span class="search">⌕ 满意度</span></div>
          <div class="chips"><span class="on">全部</span><span>教育</span><span>行政</span><span>活动</span></div>
          <div class="tpls">
            <div class="tp" :class="hl('card')"><i style="background:#d9f0e6"></i><b>{{ path.includes('满意度') ? '食堂满意度' : '家长回执' }}</b><span>12 题 · 2 分钟</span></div>
            <div class="tp"><i style="background:#e6ecfa"></i><b>社团招新报名</b><span>8 题</span></div>
            <div class="tp"><i style="background:#f8ecdc"></i><b>访谈对象招募</b><span>逻辑跳转</span></div>
            <div class="tp" v-if="!m"><i style="background:#f2e6f5"></i><b>活动签到</b><span>二维码</span></div>
          </div>
        </div>
      </template>

      <!-- 编辑器 -->
      <template v-else-if="screen === 'editor'">
        <div class="ed">
          <div v-if="!m" class="ed-side"><b>字段</b><span>单行文本</span><span>单选</span><span>多选</span><span>日期</span><span>签名</span></div>
          <div class="ed-main">
            <div class="ed-title">{{ path.includes('club') ? '社团招新报名' : path.includes('canteen') ? '三号厂区食堂满意度' : path.includes('recruit') ? '访谈对象招募' : '家长回执' }}</div>
            <div class="fld"><span class="grip">⋮⋮</span>姓名<i></i></div>
            <div class="fld"><span class="grip">⋮⋮</span>{{ path.includes('club') ? '专业' : '联系电话' }}<i></i></div>
            <div class="fld" :class="hl('drag')"><span class="grip">⋮⋮</span>{{ path.includes('club') ? '年级' : '签名' }}<i></i></div>
            <div class="add">＋ 添加字段</div>
          </div>
          <span class="b pri sm pub" :class="hl('publish')">发布</span>
        </div>
      </template>

      <!-- 分享 -->
      <template v-else-if="screen === 'share'">
        <div class="pg share">
          <div class="ok">✓ 已发布</div>
          <div class="link"><span>qingtan.test/f/{{ path.split('/')[2] || 'f_c20' }}</span><span class="b sm" :class="hl('copy')">复制链接</span></div>
          <div class="qr" :class="hl('qr')"><i v-for="i in 25" :key="i" :class="{ k: [1,2,3,5,6,8,11,13,15,16,19,21,22,24,25,7,18].includes(i) }"></i></div>
          <div class="fine">微信扫码即可填写</div>
        </div>
      </template>

      <!-- 填写页 -->
      <template v-else-if="screen === 'fill'">
        <div class="fill">
          <div class="h2">三号厂区食堂满意度</div>
          <div class="q">1. 你对今天午餐的满意度？</div>
          <div class="stars">★★★★☆</div>
          <div class="q">2. 想对食堂说的话</div><div class="in"></div>
          <span class="b pri full">提交</span>
        </div>
      </template>

      <!-- 微信内打开显示桌面布局 -->
      <template v-else-if="screen === 'wechat'">
        <div class="wx" :class="hl('page')">
          <div class="wx-desk">
            <div class="mk-nav"><span class="brand"><i class="leaf"></i>青檀表单</span><span class="sp"></span><span class="lnk">登录</span></div>
            <div class="wx-cols"><div><b>社团招新报名</b><div class="in"></div><div class="in"></div><div class="in"></div></div><div class="side"></div></div>
          </div>
        </div>
      </template>

      <!-- 回复页 / 更多菜单 / 导出成功 -->
      <template v-else-if="['responses','more-menu','export-done'].includes(screen)">
        <div class="pg resp">
          <div v-if="m" class="banner" :class="hl('banner')">升级专业版，解锁更多数据能力 →</div>
          <div class="pg-h" :class="hl('toolbar')">
            <b>回复 · {{ path.includes('8a1') ? '门店巡检反馈' : path.includes('2b6') ? '门店周反馈' : '我的表单' }}</b>
            <span class="live-badge" :class="hl('live')"><i></i>实时</span>
            <span class="sp"></span>
            <span class="tb" v-if="!m">筛选</span>
            <span class="tb more" v-if="!m" :class="hl('more')">⋯ 更多</span>
          </div>
          <div class="tbl" :class="hl('table')">
            <div class="tr th"><span>#</span><span>门店</span><span v-if="!m">评分</span><span>提交时间</span></div>
            <div class="tr" v-for="i in (m ? 6 : 5)" :key="i"><span>{{ 127 - i }}</span><span>{{ ['西湖店','滨江店','萧山店','余杭店','拱墅店','上城店'][i-1] }}</span><span v-if="!m">{{ [5,4,4,3,5][i-1] }}</span><span>10-0{{ i }} 2{{ i }}:1{{ i }}</span></div>
          </div>
          <div v-if="screen === 'more-menu'" class="menu">
            <span>打印</span><span :class="hl('export')">导出为 Excel</span><span>数据清理</span><span>回复设置</span>
          </div>
          <div v-if="screen === 'export-done'" class="toast" :class="hl('toast')">✓ 已导出「回复数据.xlsx」 1.2 MB</div>
        </div>
      </template>

      <!-- 看板 -->
      <template v-else-if="screen === 'insights' || screen === 'dark-chart'">
        <div class="pg">
          <div class="pg-h"><b>数据看板</b><span class="sp"></span><span class="tb">近 7 天</span></div>
          <div class="chart">
            <div class="bars"><i v-for="(h, i) in [40, 62, 55, 80, 72, 90, 66]" :key="i" :style="{ height: h + '%' }"></i></div>
            <div class="axis" :class="hl('axis')"><span v-for="d in ['周一','周二','周三','周四','周五','周六','周日']" :key="d">{{ d }}</span></div>
          </div>
        </div>
      </template>

      <!-- 价格页 -->
      <template v-else-if="screen === 'pricing'">
        <div class="mk-nav"><span class="brand"><i class="leaf"></i>青檀表单</span><span class="sp"></span><span class="lnk">返回</span></div>
        <div class="price">
          <div class="h2 c">选择适合你的方案</div>
          <div class="cycle"><span class="on">月付</span><span>年付 · 最高 8 折</span></div>
          <div class="plans">
            <div class="plan" v-if="!m"><b>免费版</b><div class="amt">¥0</div><span>每月 200 条回复</span></div>
            <div class="plan pro">
              <b>专业版</b>
              <div class="amt" :class="hl('seat')">¥39<small>/席位/月起</small></div>
              <span class="usage" :class="hl('usage')">含每月 1 万条回复，超出按 ¥0.004/条计费*</span>
              <span class="b pri full" :class="hl('upgrade')">升级专业版</span>
            </div>
            <div class="plan" v-if="!m"><b>企业版</b><div class="amt">联系我们</div><span>私有部署</span></div>
          </div>
          <div class="fine">* 计费说明 ▾</div>
        </div>
      </template>

      <!-- 结账 -->
      <template v-else-if="screen === 'checkout' || screen === 'checkout-done'">
        <div class="pg co">
          <template v-if="screen === 'checkout'">
            <div class="h2">升级专业版 <span class="sandbox">沙箱</span></div>
            <div class="co-row"><span>席位</span><b>5</b></div>
            <div class="co-row"><span>席位费 ¥39 × 5</span><b>¥195</b></div>
            <div class="co-row"><span>预估超量回复（2.3 万条）</span><b>¥92</b></div>
            <div class="co-row tot" :class="hl('total')"><span>合计 / 月</span><b>¥287</b></div>
            <div class="co-row"><span>发票抬头</span><b class="inv">深圳某某科技有限公司 ✎</b></div>
            <span class="b pri full">确认支付</span>
          </template>
          <template v-else>
            <div class="okbig">✓</div><div class="h2 c">已升级为专业版</div><div class="fine c">沙箱订单 #SBX-20261003-0187</div>
          </template>
        </div>
      </template>

      <!-- 团队 -->
      <template v-else-if="screen === 'team' || screen === 'team-error'">
        <div class="pg">
          <div class="pg-h"><b>团队成员</b><span class="sp"></span><span class="b pri sm" :class="hl('invite')">邀请成员</span></div>
          <div class="tbl"><div class="tr"><span>孙立行</span><span>所有者</span></div><div class="tr"><span>—</span><span></span></div></div>
          <div class="dialog">
            <b>邀请成员</b><div class="in">qa-invite@qingtan.test</div><span class="b pri sm">发送邀请</span>
          </div>
          <div v-if="screen === 'team-error'" class="toast err" :class="hl('toast')">请稍后再试</div>
        </div>
      </template>

      <!-- 帮助 -->
      <template v-else-if="screen === 'help'">
        <div class="pg"><div class="pg-h"><b>帮助中心 · 逻辑跳转</b></div><div class="doc"><i></i><i></i><i class="s"></i><i></i><i class="s"></i></div></div>
      </template>
    </div>

    <svg v-if="target" class="cursor" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 1l11 6.5-4.6 1.1L6.6 13z" fill="#111" stroke="#fff" stroke-width="1"/></svg>
  </div>
</template>

<style scoped>
.shot {
  --q-bg: #ffffff; --q-bg2: #f5f6f4; --q-text: #1f2328; --q-mut: #6b7280; --q-line: #e3e5e1; --q-brand: #127a5a; --q-brand-soft: #e0f2ea; --q-err: #c93a2c;
  container-type: inline-size; position: relative; background: var(--q-bg); color: var(--q-text);
  border: 1px solid var(--border); border-radius: var(--r-md); overflow: hidden; font-family: var(--font-sans);
  aspect-ratio: 16 / 10.4; display: flex; flex-direction: column; line-height: 1.4; user-select: none;
}
.shot > * { font-size: 1.62cqw; }
.shot.m { aspect-ratio: 9 / 17.5; border-radius: 18px; border: 6px solid #1b1b1b; }
.shot.m > * { font-size: 4.2cqw; }
.shot.dark { --q-bg: #16181b; --q-bg2: #1f2226; --q-text: #e7e7e5; --q-mut: #4a4f57; --q-line: #2b2f34; }

.chrome { display: flex; align-items: center; gap: 1em; padding: .55em .9em; background: #ecedea; border-bottom: 1px solid #dcdcd8; }
.lights { display: flex; gap: .35em; }
.lights i { width: .7em; height: .7em; border-radius: 50%; background: #d4d4cf; display: block; }
.url { flex: 1; background: #fff; border-radius: .5em; padding: .2em .8em; color: #555; font-family: var(--font-mono); font-size: .9em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lock { font-size: .6em; margin-right: .5em; color: #2e7d4f; vertical-align: middle; }
.phone-top { display: flex; justify-content: space-between; align-items: center; padding: .5em 1.1em .3em; font-size: .8em !important; font-weight: 600; background: var(--q-bg); }
.notch { width: 30%; height: .9em; background: #1b1b1b; border-radius: 1em; }
.m-url { margin: 0 .8em .4em; background: var(--q-bg2); border-radius: .6em; padding: .25em .7em; font-family: var(--font-mono); font-size: .72em !important; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wx-bar { display: flex; justify-content: space-between; padding: .4em 1em; background: #ededed; font-size: .85em !important; }

.vp { flex: 1; position: relative; overflow: hidden; background: var(--q-bg); }
.sp { flex: 1; }
.brand { display: inline-flex; align-items: center; gap: .4em; font-weight: 700; }
.brand.c { justify-content: center; width: 100%; margin-bottom: .8em; }
.leaf { width: .9em; height: .9em; background: var(--q-brand); border-radius: .2em .9em .2em .9em; display: inline-block; }
.appbar { display: flex; align-items: center; gap: 1.4em; padding: .7em 1.2em; border-bottom: 1px solid var(--q-line); }
.nav { display: flex; gap: 1.2em; color: var(--q-mut); }
.nav b { color: var(--q-text); }
.up { color: var(--q-brand); font-weight: 600; }
.me { width: 1.6em; height: 1.6em; border-radius: 50%; background: var(--q-bg2); display: grid; place-items: center; font-size: .8em; }
.b { display: inline-flex; align-items: center; justify-content: center; padding: .45em 1em; border-radius: .45em; border: 1px solid var(--q-line); font-weight: 600; white-space: nowrap; }
.b.pri { background: var(--q-brand); color: #fff; border-color: var(--q-brand); }
.b.sm { padding: .3em .8em; font-size: .9em; }
.b.full { width: 100%; margin-top: .8em; }
.row-btn { display: flex; gap: .7em; margin-top: 1.2em; align-items: center; }
.row-btn.end { justify-content: flex-end; }
.h1 { font-size: 2.2em; font-weight: 800; line-height: 1.2; letter-spacing: -.01em; }
.h2 { font-size: 1.35em; font-weight: 700; margin-bottom: .6em; }
.c { text-align: center; }
.p { color: var(--q-mut); margin-top: .6em; }
.fine { color: var(--q-mut); font-size: .85em; margin-top: .8em; }
.in { border: 1px solid var(--q-line); border-radius: .45em; height: 2.2em; margin-top: .6em; padding: 0 .8em; display: flex; align-items: center; color: var(--q-mut); font-size: .95em; }
.in.err { border-color: var(--q-err); }
.errtxt { color: var(--q-err); font-size: .85em; margin-top: .3em; }
.hint { color: var(--q-mut); font-size: .8em; margin-top: .3em; }

.mk-nav { display: flex; align-items: center; gap: 1.4em; padding: .8em 1.4em; }
.lnk { color: var(--q-mut); }
.lnk.login { color: var(--q-text); font-weight: 600; border: 1px solid var(--q-line); padding: .2em .8em; border-radius: .4em; }
.hero { padding: 2.2em 1.4em; text-align: center; display: flex; flex-direction: column; align-items: center; }
.mock-form { margin-top: 2em; width: 60%; border: 1px solid var(--q-line); border-radius: .8em; padding: 1em; display: grid; gap: .6em; background: var(--q-bg2); }
.m .mock-form { width: 90%; }
.mock-form i, .doc i { display: block; height: .9em; border-radius: .3em; background: #dfe3dc; }
.mock-form i.s, .doc i.s { width: 60%; }
.auth { width: 46%; margin: 2.2em auto; }
.m .auth { width: 86%; margin-top: 1.4em; }

.mail { padding: 1em 1.2em; }
.mail-h { font-weight: 700; margin-bottom: .6em; }
.mail-h span { background: var(--q-brand); color: #fff; border-radius: 1em; padding: 0 .5em; font-size: .8em; }
.mail-row { border-bottom: 1px solid var(--q-line); padding: .7em 0; display: flex; justify-content: space-between; flex-wrap: wrap; gap: .4em; }
.mail-row span { color: var(--q-mut); font-size: .85em; }
.mail-row.open { display: block; background: var(--q-bg2); padding: .8em; border-radius: .5em; }
.mail-body { color: var(--q-mut); margin-top: .5em; display: flex; flex-direction: column; align-items: flex-start; gap: .7em; }

.onb { width: 56%; margin: 2em auto; }
.m .onb { width: 88%; }
.stepper { display: flex; gap: .4em; margin-bottom: 1em; }
.stepper i { flex: 1; height: .3em; border-radius: 1em; background: var(--q-line); display: block; }
.stepper i.on { background: var(--q-brand); }
.opts { display: grid; grid-template-columns: 1fr 1fr; gap: .6em; }
.opts span { border: 1px solid var(--q-line); border-radius: .5em; padding: .8em; }
.skip { font-size: .62em; color: var(--q-mut); padding: .2em; }

.pg { padding: 1em 1.2em; position: relative; height: 100%; }
.pg-h { display: flex; align-items: center; gap: .8em; margin-bottom: .9em; }
.pg-h b { font-size: 1.1em; }
.cards, .tpls { display: grid; grid-template-columns: repeat(3, 1fr); gap: .8em; }
.m .cards, .m .tpls { grid-template-columns: 1fr; }
.m .tpls { grid-template-columns: 1fr 1fr; }
.fc { border: 1px solid var(--q-line); border-radius: .6em; padding: .9em; display: flex; flex-direction: column; gap: .3em; }
.fc span, .tp span { color: var(--q-mut); font-size: .85em; }
.fc.dim { opacity: .55; }
.tpls { grid-template-columns: repeat(4, 1fr); }
.tp { border: 1px solid var(--q-line); border-radius: .6em; padding: .6em; display: flex; flex-direction: column; gap: .2em; }
.tp i { height: 3.2em; border-radius: .4em; display: block; margin-bottom: .3em; }
.search { border: 1px solid var(--q-line); border-radius: .4em; padding: .2em .7em; color: var(--q-mut); margin-left: auto; }
.chips { display: flex; gap: .5em; margin-bottom: .8em; }
.chips span { padding: .2em .7em; border-radius: 1em; background: var(--q-bg2); font-size: .85em; }
.chips .on { background: var(--q-brand-soft); color: var(--q-brand); font-weight: 600; }

.ed { display: flex; height: 100%; position: relative; }
.ed-side { width: 22%; border-right: 1px solid var(--q-line); padding: 1em; display: flex; flex-direction: column; gap: .5em; color: var(--q-mut); }
.ed-side b { color: var(--q-text); }
.ed-side span { border: 1px dashed var(--q-line); border-radius: .4em; padding: .3em .6em; }
.ed-main { flex: 1; padding: 1.2em 1.4em; display: flex; flex-direction: column; gap: .6em; background: var(--q-bg2); }
.ed-title { font-weight: 700; font-size: 1.2em; margin-bottom: .2em; }
.fld { background: var(--q-bg); border: 1px solid var(--q-line); border-radius: .5em; padding: .7em .8em; display: flex; flex-direction: column; gap: .4em; position: relative; padding-left: 2em; }
.fld i { height: 1.4em; border: 1px solid var(--q-line); border-radius: .3em; display: block; }
.grip { position: absolute; left: .6em; top: .7em; color: #b3b7b0; letter-spacing: -.2em; }
.add { color: var(--q-brand); font-weight: 600; padding: .4em 0; }
.pub { position: absolute; right: 1.2em; top: .9em; }

.share { display: flex; flex-direction: column; align-items: center; padding-top: 1.6em; }
.ok { color: var(--q-brand); font-weight: 700; font-size: 1.2em; margin-bottom: .8em; }
.link { display: flex; align-items: center; gap: .6em; border: 1px solid var(--q-line); border-radius: .5em; padding: .3em .3em .3em .8em; font-family: var(--font-mono); font-size: .9em; }
.qr { display: grid; grid-template-columns: repeat(5, 1fr); gap: .15em; width: 7em; height: 7em; margin-top: 1.2em; padding: .5em; border: 1px solid var(--q-line); border-radius: .4em; }
.qr i { background: #eee; display: block; }
.qr i.k { background: #1f2328; }

.fill { width: 50%; margin: 1.6em auto; }
.m .fill { width: 88%; }
.q { margin-top: 1em; font-weight: 600; }
.stars { color: #e3a008; font-size: 1.4em; margin-top: .3em; }

.wx { padding: .6em; height: 100%; }
.wx-desk { transform-origin: top left; width: 250%; transform: scale(.4); }
.wx-desk .mk-nav { font-size: 1em; }
.wx-cols { display: grid; grid-template-columns: 2fr 1fr; gap: 1em; padding: 1em 1.4em; }
.wx-cols .side { background: var(--q-bg2); border-radius: .5em; height: 14em; }

.resp .banner { background: var(--q-brand-soft); color: var(--q-brand); padding: .5em .8em; border-radius: .5em; margin-bottom: .8em; font-weight: 600; font-size: .9em; }
.live-badge { display: inline-flex; align-items: center; gap: .3em; color: var(--q-brand); font-size: .8em; font-weight: 600; background: var(--q-brand-soft); padding: .1em .5em; border-radius: 1em; }
.live-badge i { width: .45em; height: .45em; border-radius: 50%; background: var(--q-brand); display: block; }
.tb { border: 1px solid var(--q-line); border-radius: .4em; padding: .2em .7em; color: var(--q-mut); }
.tbl { border: 1px solid var(--q-line); border-radius: .5em; overflow: hidden; }
.tr { display: grid; grid-template-columns: .6fr 1.4fr 1fr 1.6fr; padding: .5em .8em; border-bottom: 1px solid var(--q-line); font-size: .9em; }
.m .tr { grid-template-columns: .6fr 1.4fr 1.8fr; }
.tr:last-child { border-bottom: none; }
.tr.th { background: var(--q-bg2); color: var(--q-mut); font-weight: 600; }
.menu { position: absolute; right: 1.2em; top: 3.2em; background: var(--q-bg); border: 1px solid var(--q-line); border-radius: .5em; box-shadow: 0 .5em 1.5em rgba(0,0,0,.12); display: flex; flex-direction: column; padding: .3em; min-width: 9em; }
.menu span { padding: .4em .7em; border-radius: .3em; }
.toast { position: absolute; left: 50%; bottom: 1.2em; transform: translateX(-50%); background: #1f2328; color: #fff; padding: .5em 1em; border-radius: .5em; white-space: nowrap; font-size: .9em; }
.toast.err { background: #3a1f1d; color: #ffd9d4; }

.chart { border: 1px solid var(--q-line); border-radius: .6em; padding: 1em; height: 72%; display: flex; flex-direction: column; }
.bars { flex: 1; display: flex; align-items: flex-end; gap: 4%; padding: 0 2%; }
.bars i { flex: 1; background: var(--q-brand); border-radius: .3em .3em 0 0; display: block; opacity: .85; }
.axis { display: flex; justify-content: space-around; color: var(--q-mut); font-size: .85em; margin-top: .4em; }

.price { padding: .6em 1.4em; }
.cycle { display: flex; justify-content: center; gap: .4em; margin-bottom: 1em; }
.cycle span { padding: .2em .8em; border-radius: 1em; background: var(--q-bg2); font-size: .85em; }
.cycle .on { background: var(--q-text); color: var(--q-bg); }
.plans { display: grid; grid-template-columns: 1fr 1.2fr 1fr; gap: 1em; align-items: start; }
.m .plans { grid-template-columns: 1fr; }
.plan { border: 1px solid var(--q-line); border-radius: .7em; padding: 1em; display: flex; flex-direction: column; gap: .4em; }
.plan span { color: var(--q-mut); font-size: .85em; }
.plan.pro { border-color: var(--q-brand); box-shadow: 0 0 0 1px var(--q-brand); }
.amt { font-size: 1.8em; font-weight: 800; }
.amt small { font-size: .45em; font-weight: 500; color: var(--q-mut); }
.usage { line-height: 1.5; }

.co { width: 56%; margin: 0 auto; padding-top: 1.4em; }
.m .co { width: 92%; }
.sandbox { font-size: .6em; background: #fff3cd; color: #8a6d00; padding: .1em .5em; border-radius: .3em; vertical-align: middle; }
.co-row { display: flex; justify-content: space-between; padding: .55em 0; border-bottom: 1px solid var(--q-line); }
.co-row span { color: var(--q-mut); }
.co-row.tot b { font-size: 1.3em; }
.inv { font-weight: 500; }
.okbig { width: 2.6em; height: 2.6em; border-radius: 50%; background: var(--q-brand); color: #fff; display: grid; place-items: center; font-size: 1.4em; margin: 1.6em auto .8em; }

.dialog { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); background: var(--q-bg); border: 1px solid var(--q-line); border-radius: .7em; box-shadow: 0 1em 2em rgba(0,0,0,.15); padding: 1em; width: 55%; display: flex; flex-direction: column; gap: .4em; align-items: flex-start; }
.dialog .in { width: 100%; }
.doc { display: grid; gap: .7em; max-width: 70%; }

/* —— 标注：人物在这一步操作的位置 —— */
.hl { outline: 2px solid #111; outline-offset: 2px; box-shadow: 0 0 0 5px rgba(255,255,255,.9), 0 0 0 7px rgba(17,17,17,.25); position: relative; z-index: 2; border-radius: .4em; }
.dark .hl { outline-color: #fff; box-shadow: 0 0 0 5px rgba(0,0,0,.6), 0 0 0 7px rgba(255,255,255,.3); }
.cursor { position: absolute; width: 3.2%; right: 6%; bottom: 8%; filter: drop-shadow(0 1px 1px rgba(0,0,0,.3)); display: none; }
.m .cursor { width: 9%; }
.live .cursor { display: block; animation: hover 1.8s var(--ease) infinite; }
@keyframes hover { 50% { transform: translate(-6px, -4px); } }
@media (prefers-reduced-motion: reduce) { .live .cursor { animation: none; } }
</style>
