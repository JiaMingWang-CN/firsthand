// 演示数据：虚构产品「青檀表单」的一次完整运行。
// 时间统一用“模拟分钟”：D1 00:00 = 0，D1 21:10 = 1270。
// 结构对齐 docs/plan.md 4.5（人物）、4.9（体验记录 / 表达过滤）、4.10（离场问卷）。

export const product = {
  name: '青檀表单',
  version: 'v2.4',
  url: 'https://demo.qingtan.test',
  positioning: '面向中小团队的在线表单与数据收集工具：搭表单、分享链接、实时看回复、导出数据。',
  targetUsers: '运营、HR、教师、产品与研究人员；工作日白天桌面为主，通勤与晚间常用手机。',
  allowedDomains: ['demo.qingtan.test', 'mail.qingtan.test'],
  forbidden: ['真实支付（仅允许沙箱结账页）', '删除他人表单或回复', '向外部邮箱发送邀请'],
  accounts: [
    { role: 'new_visitor', desc: '无账号，从注册开始' },
    { role: 'free_user', desc: '免费版测试账号，已有 2 张表单、126 条回复' },
  ],
}

export const flows = [
  { id: 'F1', name: '注册并完成新手引导', short: '注册引导' },
  { id: 'F2', name: '创建并分享第一张表单', short: '创建分享' },
  { id: 'F3', name: '导出回复数据', short: '导出数据' },
  { id: 'F4', name: '升级到专业版', short: '升级付费' },
]

// —— 人物 ——
export const personas = [
  {
    id: 'p1', color: 'var(--p1)', realname: '林晓雯', username: 'xiaowen_lin', gender: '女', age: 34, city: '杭州', timezone: 'Asia/Shanghai',
    profession: '电商运营主管', industry: '零售', education: '本科', income: '中',
    life: '两个孩子的妈妈，工作日晚上才有自己的时间。',
    history: '用过竞品「麦表」一年，嫌贵才转过来试用。',
    bio: '电商运营，每周要收几十份门店反馈表，习惯手机上处理。',
    mbti: 'ESTJ', bigFive: { O: '中', C: '高', E: '中', A: '低', N: '中' }, style: '直接，爱吐槽',
    device: 'mobile', tech: 'normal', patience: 'low', maxSteps: 15, stall: 4, motivation: '有明确任务',
    account: 'free_user', tools: [], assignment: 'F3',
    wake: '06:30', sleep: '23:30', slot: 1270, state: '带完孩子，有点累，只想十分钟内把门店反馈导出来。',
    participation: 'commenter', candor: '中', withhold: '高', withholdReasons: ['没搞懂会显得自己不会用', '不想得罪人'],
    activity: { 7: .2, 8: .2, 12: .5, 13: .3, 21: .9, 22: .8 },
    outcome: 'quit', outcomeReason: '在手机回复页找了 6 分钟没有找到导出入口，放弃。',
  },
  {
    id: 'p2', color: 'var(--p2)', realname: '周远', username: 'zhouyuan_fe', gender: '男', age: 29, city: '上海', timezone: 'Asia/Shanghai',
    profession: '前端工程师', industry: '互联网', education: '硕士', income: '中高',
    life: '在一家 B2B 公司做前端，团队想把内部问卷从自建系统迁走。',
    history: '自己写过表单引擎，对表单产品的交互细节很挑剔。',
    bio: '前端，喜欢拆别人家的产品看实现。',
    mbti: 'INTP', bigFive: { O: '高', C: '中', E: '低', A: '中', N: '低' }, style: '直接，克制',
    device: 'desktop', tech: 'developer', patience: 'high', maxSteps: 80, stall: 10, motivation: '对比竞品',
    account: 'new_visitor', tools: ['read_console', 'list_failed_requests'], assignment: 'F1',
    wake: '08:30', sleep: '01:00', slot: 620, state: '上午刚开完站会，精神好，有耐心逐项看。',
    participation: 'poster', candor: '高', withhold: '低', withholdReasons: [],
    activity: { 10: .5, 11: .6, 12: .8, 13: .7, 14: .6, 17: .5, 22: .4 },
    outcome: 'success', outcomeReason: '完成注册；验证后被带回首页，重新登录后完成引导。',
  },
  {
    id: 'p3', color: 'var(--p3)', realname: '陈默', username: 'chenmo_store', gender: '男', age: 41, city: '成都', timezone: 'Asia/Shanghai',
    profession: '连锁餐饮门店经理', industry: '餐饮', education: '大专', income: '中',
    life: '管 3 家门店，午休 40 分钟是一天里唯一能坐下来的时间。',
    history: '之前用纸质表和微信群接龙收员工排班意向。',
    bio: '开店的，想找个能让员工手机上填排班的东西。',
    mbti: 'ESFP', bigFive: { O: '中', C: '中', E: '高', A: '高', N: '中' }, style: '爱吐槽，口语化',
    device: 'mobile', tech: 'novice', patience: 'low', maxSteps: 15, stall: 3, motivation: '随便看看',
    account: 'new_visitor', tools: [], assignment: 'F1',
    wake: '07:00', sleep: '23:00', slot: 790, state: '午休，刚吃完饭，一边刷手机一边等下午开会。',
    participation: 'poster', candor: '高', withhold: '中', withholdReasons: ['怕被笑话'],
    activity: { 8: .3, 12: .7, 13: .8, 14: .4, 21: .6, 22: .5 },
    outcome: 'quit', outcomeReason: '验证后回到首页，以为没注册成功；重新注册提示邮箱已存在，放弃。',
  },
  {
    id: 'p4', color: 'var(--p4)', realname: '赵一苇', username: 'yiwei_ux', gender: '女', age: 26, city: '北京', timezone: 'Asia/Shanghai',
    profession: '用户研究员', industry: '互联网', education: '硕士', income: '中',
    life: '每月要招募 20+ 名访谈对象，筛选问卷是日常。',
    history: '常用问卷星和飞书表单，关心逻辑跳转和数据看板。',
    bio: '做用研的，对问卷工具有职业病。',
    mbti: 'INFJ', bigFive: { O: '高', C: '高', E: '中', A: '高', N: '低' }, style: '委婉，爱夸',
    device: 'desktop', tech: 'normal', patience: 'high', maxSteps: 80, stall: 10, motivation: '对比竞品',
    account: 'new_visitor', tools: [], assignment: 'explore',
    wake: '08:00', sleep: '00:30', slot: 870, state: '下午没有会，专门留了一小时评估工具。',
    participation: 'commenter', candor: '高', withhold: '低', withholdReasons: [],
    activity: { 9: .4, 12: .5, 15: .7, 16: .6, 20: .5 },
    outcome: 'success', outcomeReason: '自由探索 14 步，完成注册、模板建表与回复看板。',
  },
  {
    id: 'p5', color: 'var(--p5)', realname: '吴桐', username: 'wutong_admin', gender: '男', age: 52, city: '苏州', timezone: 'Asia/Shanghai',
    profession: '制造业行政主管', industry: '制造业', education: '本科', income: '中',
    life: '负责厂区食堂满意度调查、活动报名，电脑操作靠摸索。',
    history: '一直用 Excel 收集，再手工汇总。',
    bio: '行政，想把食堂调查从 Excel 换成线上。',
    mbti: 'ISTJ', bigFive: { O: '低', C: '高', E: '低', A: '中', N: '中' }, style: '委婉，话少',
    device: 'desktop', tech: 'novice', patience: 'normal', maxSteps: 40, stall: 6, motivation: '有明确任务',
    account: 'free_user', tools: [], assignment: 'F2',
    wake: '06:00', sleep: '22:00', slot: 555, state: '上班刚处理完邮件，办公室安静。',
    participation: 'lurker', candor: '低', withhold: '高', withholdReasons: ['觉得是自己操作不熟练', '不习惯在网上发言'],
    activity: { 8: .3, 9: .3, 13: .5, 14: .4, 19: .3 },
    outcome: 'success', outcomeReason: '用模板创建了食堂满意度表单并复制了分享链接，共 13 步。',
  },
  {
    id: 'p6', color: 'var(--p6)', realname: '郑可', username: 'zhengke_pm', gender: '女', age: 31, city: '深圳', timezone: 'Asia/Shanghai',
    profession: 'SaaS 产品经理', industry: '企业服务', education: '本科', income: '中高',
    life: '负责团队工具采购评估，需要给老板一个明确的月费数字。',
    history: '做了 8 年 SaaS，对定价页有自己的一套判断。',
    bio: 'SaaS 产品经理，看定价页比看功能页还仔细。',
    mbti: 'ENTJ', bigFive: { O: '高', C: '高', E: '高', A: '低', N: '低' }, style: '直接，结构化',
    device: 'desktop', tech: 'normal', patience: 'normal', maxSteps: 40, stall: 6, motivation: '付费决策',
    account: 'free_user', tools: [], assignment: 'F4',
    wake: '07:30', sleep: '00:00', slot: 960, state: '下午四点，开完评审会，准备给采购结论。',
    participation: 'poster', candor: '中', withhold: '中', withholdReasons: ['涉及公司财务信息'],
    activity: { 9: .4, 12: .5, 17: .8, 18: .6, 22: .5 },
    outcome: 'success', outcomeReason: '在沙箱结账页完成升级；价格在第 9 步才算清楚。',
  },
  {
    id: 'p7', color: 'var(--p7)', realname: '王思源', username: 'siyuan_club', gender: '男', age: 22, city: '武汉', timezone: 'Asia/Shanghai',
    profession: '大四学生 · 社团负责人', industry: '学生', education: '本科在读', income: '低',
    life: '社团招新季，要在群里发报名表；习惯深夜处理社团事务。',
    history: '用过腾讯问卷，觉得「能用就行」。',
    bio: '社团负责人，夜猫子。',
    mbti: 'ENFP', bigFive: { O: '高', C: '低', E: '高', A: '高', N: '中' }, style: '爱夸，随意',
    device: 'mobile', tech: 'normal', patience: 'low', maxSteps: 15, stall: 3, motivation: '有明确任务',
    account: 'free_user', tools: [], assignment: 'F2',
    wake: '10:00', sleep: '02:30', slot: 1420, state: '深夜 23:40，困，躺在床上用手机赶在睡前发报名表。',
    participation: 'reactor', candor: '高', withhold: '低', withholdReasons: [],
    activity: { 11: .3, 14: .3, 20: .4, 22: .6, 23: .9 },
    outcome: 'success', outcomeReason: '勉强完成：拖拽字段失败后改用「添加字段」，分享链接在微信内显示桌面布局。',
  },
  {
    id: 'p8', color: 'var(--p8)', realname: '何佳', username: 'hejia_photo', gender: '女', age: 37, city: '广州', timezone: 'Asia/Shanghai',
    profession: '独立摄影师', industry: '自由职业', education: '本科', income: '中',
    life: '接约拍单，想用表单收客户档期和需求，偶尔考虑付费工具。',
    history: '一直用微信手动沟通，没用过表单工具。',
    bio: '摄影师，想省掉来回问档期的时间。',
    mbti: 'ISFP', bigFive: { O: '高', C: '低', E: '低', A: '高', N: '高' }, style: '委婉',
    device: 'mobile', tech: 'novice', patience: 'normal', maxSteps: 40, stall: 6, motivation: '付费决策',
    account: 'free_user', tools: [], assignment: 'F4',
    wake: '09:00', sleep: '01:00', slot: 1170, state: '刚修完一组片，晚饭后有点空，用手机看看。',
    participation: 'lurker', candor: '低', withhold: '高', withholdReasons: ['不想显得外行', '不习惯公开发言'],
    activity: { 11: .3, 15: .2, 19: .7, 20: .6, 23: .4 },
    outcome: 'quit', outcomeReason: '看了 4 遍价格页仍说不出专业版月费，放弃升级。',
  },
  {
    id: 'p9', color: 'var(--p9)', realname: '孙立行', username: 'lixing_be', gender: '男', age: 33, city: '杭州', timezone: 'Asia/Shanghai',
    profession: '后端技术负责人', industry: '物流', education: '本科', income: '高',
    life: '夜猫子，习惯凌晨处理不被打扰的事；要给运营团队选数据收集工具。',
    history: '关心导出格式、接口稳定性和权限模型。',
    bio: '后端 TL，凌晨两点也在线。',
    mbti: 'ISTP', bigFive: { O: '中', C: '高', E: '低', A: '中', N: '低' }, style: '直接，技术化',
    device: 'desktop', tech: 'developer', patience: 'high', maxSteps: 80, stall: 10, motivation: '有明确任务',
    account: 'free_user', tools: ['read_console', 'list_failed_requests'], assignment: 'F3',
    wake: '11:00', sleep: '03:00', slot: 90, state: '凌晨 01:30，刚处理完一次线上告警，头脑清醒。',
    participation: 'commenter', candor: '高', withhold: '低', withholdReasons: [],
    activity: { 0: .6, 1: .8, 2: .5, 12: .7, 13: .5, 23: .6 },
    outcome: 'success', outcomeReason: '在「⋯ 更多」菜单中找到导出；顺带发现邀请成员接口 500。',
  },
  {
    id: 'p10', color: 'var(--p10)', realname: '冯晚晴', username: 'wanqing_teacher', gender: '女', age: 28, city: '西安', timezone: 'Asia/Shanghai',
    profession: '中学语文老师', industry: '教育', education: '硕士', income: '中',
    life: '班主任，常给家长发回执和调查；早上通勤 40 分钟。',
    history: '用过金数据，对模板和移动端填写体验敏感。',
    bio: '班主任，通勤路上处理班级事务。',
    mbti: 'ENFJ', bigFive: { O: '中', C: '高', E: '高', A: '高', N: '中' }, style: '委婉，爱夸',
    device: 'mobile', tech: 'normal', patience: 'normal', maxSteps: 40, stall: 6, motivation: '随便看看',
    account: 'new_visitor', tools: [], assignment: 'explore',
    wake: '06:10', sleep: '22:30', slot: 430, state: '早上 07:10 地铁通勤，站着单手操作手机。',
    participation: 'reactor', candor: '中', withhold: '中', withholdReasons: ['不想显得挑剔'],
    activity: { 6: .4, 7: .7, 12: .4, 18: .8, 21: .5 },
    outcome: 'success', outcomeReason: '自由探索 12 步，完成注册、模板建表；拖拽字段在手机上失败。',
  },
]

// —— 体验记录：步骤日志 ——
// s(t, 动作, 画面, 路径, 满意度 -1..1, 困惑度 0..1, 心声, 额外)
const s = (t, act, screen, path, sat, conf, think, extra = {}) => ({ t, act, screen, path, sat, conf, think, ...extra })

export const steps = {
  p9: [
    s(90, '打开登录页并使用测试账号登录', 'login', '/login', .2, 0, '先看导出格式支不支持 CSV。'),
    s(91, '进入「我的表单」列表', 'dashboard', '/forms', .3, 0, '列表很干净。'),
    s(92, '打开「门店巡检反馈」的回复页', 'responses', '/forms/f_8a1/responses', .3, .1, '回复表格加载很快。', { target: 'table' }),
    s(93, '在顶部工具栏寻找「导出」按钮', 'responses', '/forms/f_8a1/responses', -.1, .4, '说明书说导出在顶部，这里没有。', { target: 'toolbar' }),
    s(94, '打开列筛选菜单，确认不在这里', 'responses', '/forms/f_8a1/responses', -.2, .5, '筛选菜单里也没有。'),
    s(95, '点开右上角「⋯ 更多」', 'more-menu', '/forms/f_8a1/responses', 0, .3, '藏在溢出菜单里。', { target: 'export' }),
    s(96, '选择「导出为 Excel」', 'export-done', '/forms/f_8a1/responses', .4, .1, '导出成功，但没有 CSV 选项。', { target: 'toast' }),
    s(98, '检查导出请求与文件头', 'export-done', '/api/v1/forms/f_8a1/export', .3, 0, '接口 200，文件 1.2 MB。', { trace: ['network:GET /api/v1/forms/f_8a1/export?fmt=xlsx 200 · 842ms'] }),
    s(100, '顺带进入「团队设置」', 'team', '/settings/team', .2, .1, '看看权限模型。'),
    s(101, '点击「邀请成员」并填写测试邮箱', 'team', '/settings/team', .1, .1, '只能填邮箱，没有角色选择。', { target: 'invite' }),
    s(102, '提交邀请，界面提示「请稍后再试」', 'team-error', '/settings/team', -.6, .3, '没有任何错误详情。', { target: 'toast', trace: ['console:error Uncaught (in promise) AxiosError: Request failed with status code 500', 'network:POST /api/v1/team/invite 500 · 1210ms'] }),
    s(104, '读取 Console 与失败请求', 'team-error', '/settings/team', -.5, 0, '服务端 500，前端吞掉了错误。', { trace: ['console:error Uncaught (in promise) AxiosError: Request failed with status code 500', 'console:warn [invite] retry disabled for 5xx', 'network:POST /api/v1/team/invite 500 · 1210ms'] }),
    s(106, '切换到深色模式查看回复看板', 'dark-chart', '/forms/f_8a1/insights', -.2, .2, '图表坐标轴文字几乎看不清。', { target: 'axis' }),
    s(108, '回到回复页，结束本次体验', 'responses', '/forms/f_8a1/responses', .1, 0, '导出能用，但入口和错误处理都欠打磨。'),
  ],
  p10: [
    s(430, '在地铁上打开官网首页', 'landing', '/', .4, 0, '首页挺清爽。'),
    s(431, '点击「免费注册」', 'signup', '/signup', .3, 0, '', { target: 'submit' }),
    s(433, '填写邮箱和密码，提交', 'signup', '/signup', .3, .1, '密码规则提示挺清楚。', { target: 'submit' }),
    s(434, '打开验证邮件，点击验证链接', 'mail', 'mail.qingtan.test/inbox', .2, .1, '', { target: 'verify' }),
    s(435, '被带回官网首页，右上角仍显示「登录」', 'landing', '/?verified=1', -.4, .7, '咦，注册成功了吗？', { target: 'login' }),
    s(437, '手动登录后进入新手引导', 'onboarding', '/welcome?step=1', .1, .3, '还好密码记得。'),
    s(439, '跳过引导，进入模板库', 'templates', '/templates', .7, 0, '家长回执模板正好能用！', { target: 'card' }),
    s(441, '选择「家长回执」模板', 'editor', '/forms/new?tpl=receipt', .6, 0, '字段都预填好了。'),
    s(443, '尝试拖拽「签名」字段到顶部', 'editor', '/forms/new?tpl=receipt', -.5, .5, '拖不动……地铁上单手更难。', { target: 'drag' }),
    s(445, '再次长按拖拽，页面跟着滚动', 'editor', '/forms/new?tpl=receipt', -.6, .6, '算了，不调顺序了。', { target: 'drag' }),
    s(447, '直接发布表单', 'share', '/forms/f_c20/share', .3, .1, '二维码可以直接发家长群。', { target: 'qr' }),
    s(449, '到站，结束本次体验', 'share', '/forms/f_c20/share', .3, 0, '模板很好，手机编辑一般。'),
  ],
  p5: [
    s(555, '使用测试账号登录', 'login', '/login', 0, .1, ''),
    s(557, '进入新手引导第 1 步', 'onboarding', '/welcome?step=1', .1, .2, '引导还挺耐心的。'),
    s(559, '引导第 3 步，尝试点击「跳过」', 'onboarding', '/welcome?step=3', -.3, .5, '这个字太小了，点了好几次。', { target: 'skip' }),
    s(561, '第三次才点中「跳过」，进入表单列表', 'dashboard', '/forms', 0, .2, ''),
    s(563, '点击「新建表单」', 'templates', '/templates', .3, .2, '有模板，不用从头做。', { target: 'card' }),
    s(565, '搜索「满意度」，选择「食堂满意度」模板', 'templates', '/templates?q=满意度', .6, .1, '正好是我要的。', { target: 'card' }),
    s(567, '修改标题为「三号厂区食堂满意度」', 'editor', '/forms/new?tpl=canteen', .4, .1, ''),
    s(570, '删除「过敏原」字段', 'editor', '/forms/new?tpl=canteen', .3, .2, '删除前还会确认，挺好。'),
    s(573, '点击「发布」', 'editor', '/forms/new?tpl=canteen', .3, .1, '', { target: 'publish' }),
    s(574, '进入分享页', 'share', '/forms/f_d71/share', .4, .1, ''),
    s(576, '点击「复制链接」', 'share', '/forms/f_d71/share', .5, 0, '复制成功有提示。', { target: 'copy' }),
    s(578, '用新标签页打开链接预览填写页', 'fill', '/f/f_d71', .5, 0, '员工应该会填。'),
    s(580, '结束本次体验', 'share', '/forms/f_d71/share', .4, 0, '比 Excel 省事。'),
  ],
  p2: [
    s(620, '打开官网首页', 'landing', '/', .3, 0, '先看注册路径。'),
    s(621, '点击「免费注册」', 'signup', '/signup', .3, 0, ''),
    s(622, '故意输入错误邮箱格式，查看校验', 'signup', '/signup', .5, 0, '中文校验文案清楚，失焦触发，不错。', { target: 'error' }),
    s(624, '填写正确信息并提交', 'signup', '/signup', .3, 0, '', { target: 'submit' }),
    s(625, '打开验证邮件，点击验证链接', 'mail', 'mail.qingtan.test/inbox', .2, 0, '', { target: 'verify' }),
    s(626, '被带回营销首页，右上角显示「登录」', 'landing', '/?verified=1', -.5, .6, '验证完没登录态？回跳地址丢了。', { target: 'login', trace: ['console:warn [auth] session restore skipped: missing redirect_uri', 'network:GET /auth/verify?token=… 302 → /?verified=1'] }),
    s(628, '读取 Console，确认回跳参数缺失', 'landing', '/?verified=1', -.4, .2, '前端有 warning，应该是验证后没带 redirect_uri。', { trace: ['console:warn [auth] session restore skipped: missing redirect_uri'] }),
    s(630, '手动登录', 'login', '/login', -.1, .1, ''),
    s(631, '进入新手引导，逐步完成 4 步', 'onboarding', '/welcome?step=1', .3, .1, '引导写的是 3 步，实际 4 步。'),
    s(636, '完成引导，进入表单列表', 'dashboard', '/forms', .4, 0, ''),
    s(638, '新建空白表单，体验字段配置', 'editor', '/forms/new', .6, 0, '字段面板交互很顺，键盘也能操作。'),
    s(642, '用测试数据提交 3 条回复，观察实时刷新', 'responses', '/forms/f_e02/responses', .8, 0, '回复实时推送，WebSocket 很稳。', { target: 'live' }),
    s(645, '结束本次体验', 'responses', '/forms/f_e02/responses', .5, 0, '整体靠谱，注册回跳必须修。'),
  ],
  p3: [
    s(790, '午休时在手机上打开官网', 'landing', '/', .1, .1, '看到帖子说注册有坑，试试看。'),
    s(791, '点击「免费注册」', 'signup', '/signup', .1, .1, ''),
    s(793, '输入手机常用邮箱和密码', 'signup', '/signup', 0, .2, '密码要求有点多。', { target: 'submit' }),
    s(795, '切到邮箱 App，点击验证链接', 'mail', 'mail.qingtan.test/inbox', 0, .3, '', { target: 'verify' }),
    s(796, '回到首页，没有任何「已注册」提示', 'landing', '/?verified=1', -.6, .8, '这是成功了还是没成功？', { target: 'login' }),
    s(798, '以为失败，再次点击「免费注册」', 'signup', '/signup', -.5, .7, '那我再注册一次。'),
    s(799, '提交后提示「该邮箱已注册」', 'signup-exists', '/signup', -.8, .9, '已经注册了？那刚才为什么不让我进去？', { target: 'error' }),
    s(800, '尝试点「忘记密码」，又退出', 'signup-exists', '/signup', -.8, .6, '要开会了，不弄了。'),
    s(801, '关闭页面，放弃', 'signup-exists', '/signup', -.9, .3, '太绕了。'),
  ],
  p4: [
    s(870, '打开官网首页，阅读功能介绍', 'landing', '/', .4, 0, '定位清晰。'),
    s(872, '注册账号', 'signup', '/signup', .3, 0, ''),
    s(874, '验证邮件后回到首页', 'landing', '/?verified=1', -.3, .5, '小问题，记下来。', { target: 'login' }),
    s(876, '登录并跳过新手引导', 'onboarding', '/welcome?step=1', .1, .1, ''),
    s(878, '浏览模板库', 'templates', '/templates', .8, 0, '模板分类很贴近真实场景。', { target: 'card' }),
    s(880, '选择「访谈对象招募」模板', 'editor', '/forms/new?tpl=recruit', .8, 0, '筛选题和逻辑跳转都预置了。'),
    s(884, '修改筛选条件，测试逻辑跳转', 'editor', '/forms/new?tpl=recruit', .6, .1, '逻辑跳转的配置稍微藏得深。'),
    s(887, '发布并复制链接', 'share', '/forms/f_a19/share', .6, 0, ''),
    s(889, '用另一个窗口提交 2 条测试回复', 'fill', '/f/f_a19', .5, 0, '填写页在桌面上体验很好。'),
    s(891, '打开回复看板，观察实时刷新', 'responses', '/forms/f_a19/responses', .9, 0, '回复几乎是实时出现的，太好了。', { target: 'live' }),
    s(894, '查看数据看板图表', 'insights', '/forms/f_a19/insights', .7, .1, '图表默认就够用。'),
    s(897, '尝试找「导出」，在「⋯ 更多」里找到', 'more-menu', '/forms/f_a19/responses', .2, .4, '导出有点藏。', { target: 'export' }),
    s(899, '查看帮助中心的逻辑跳转说明', 'help', '/help/logic', .4, .1, ''),
    s(902, '结束本次体验', 'insights', '/forms/f_a19/insights', .6, 0, '会推荐给团队试试。'),
  ],
  p6: [
    s(960, '登录测试账号，点击顶部「升级」', 'pricing', '/pricing', .2, .1, '先看价格。'),
    s(962, '阅读专业版价格「¥39/席位/月起」', 'pricing', '/pricing', 0, .4, '按席位？那 5 个人就是 195？', { target: 'seat' }),
    s(964, '注意到下方「每月 1 万条回复，超出按量计费」', 'pricing', '/pricing', -.3, .7, '又按回复量？两套口径叠加？', { target: 'usage' }),
    s(966, '展开「计费说明」折叠面板', 'pricing', '/pricing#faq', -.3, .6, '说明里也没有算例。'),
    s(969, '尝试找价格计算器，没有找到', 'pricing', '/pricing', -.5, .6, '这种定价至少该有个计算器。'),
    s(972, '对比年付与月付切换', 'pricing', '/pricing?cycle=year', -.2, .5, '年付折扣写的是「最高 8 折」，最高是多高？'),
    s(975, '点击「升级专业版」', 'checkout', '/checkout?plan=pro', .1, .3, '', { target: 'upgrade' }),
    s(977, '在结账页填写席位数 5', 'checkout', '/checkout?plan=pro', .2, .2, ''),
    s(979, '结账页显示合计 ¥287/月', 'checkout', '/checkout?plan=pro', .1, .3, '终于看到数字了：195 席位费 + 92 超量预估。', { target: 'total' }),
    s(982, '修改发票抬头，发现保存后不生效', 'checkout', '/checkout?plan=pro', -.4, .3, '发票抬头改不了，财务会来问。'),
    s(985, '在沙箱环境完成支付', 'checkout-done', '/checkout/success', .3, .1, '升级本身很顺。'),
    s(987, '结束本次体验', 'checkout-done', '/checkout/success', .1, 0, '产品不错，价格页劝退。'),
  ],
  p8: [
    s(1170, '用手机打开官网，点「价格」', 'pricing', '/pricing', 0, .3, '刚看到有人说价格看不懂……', { device: 'mobile' }),
    s(1172, '阅读专业版价格', 'pricing', '/pricing', -.2, .6, '39 是一个人还是一个月？', { target: 'seat' }),
    s(1174, '上下滑动，看到按回复量计费', 'pricing', '/pricing', -.4, .8, '我一个人用，回复量是什么意思？', { target: 'usage' }),
    s(1177, '返回顶部再读一遍', 'pricing', '/pricing', -.5, .8, '还是没懂。'),
    s(1180, '点开「计费说明」', 'pricing', '/pricing#faq', -.5, .7, '全是术语。'),
    s(1183, '第 4 次阅读价格卡片', 'pricing', '/pricing', -.7, .8, '我算不出一个月要花多少钱。'),
    s(1185, '关闭页面，放弃升级', 'pricing', '/pricing', -.8, .3, '算了，先用微信吧。'),
  ],
  p1: [
    s(1270, '手机上登录测试账号', 'login', '/login', 0, .1, '赶紧弄完睡觉。'),
    s(1271, '进入「门店周反馈」表单', 'dashboard', '/forms', .1, .1, ''),
    s(1272, '打开回复页', 'responses', '/forms/f_2b6/responses', 0, .2, '数据都在，导出在哪？', { target: 'table' }),
    s(1273, '回复页顶部出现「升级专业版」横幅', 'responses', '/forms/f_2b6/responses', -.3, .5, '导出要付费？', { target: 'banner' }),
    s(1274, '向下滑动寻找导出按钮', 'responses', '/forms/f_2b6/responses', -.4, .6, '没有。'),
    s(1275, '点开左上角菜单', 'responses', '/forms/f_2b6/responses', -.4, .6, '菜单里也没有。'),
    s(1276, '点进单条回复详情，又返回', 'responses', '/forms/f_2b6/responses', -.5, .7, ''),
    s(1277, '尝试横屏，希望出现更多按钮', 'responses', '/forms/f_2b6/responses', -.6, .7, '横过来还是没有。'),
    s(1279, '再次检查顶部工具栏', 'responses', '/forms/f_2b6/responses', -.7, .8, '是不是我不会用……', { target: 'toolbar' }),
    s(1280, '放弃，关闭页面', 'responses', '/forms/f_2b6/responses', -.8, .4, '明天去电脑上弄吧。'),
  ],
  p7: [
    s(1420, '躺床上用手机登录', 'login', '/login', .1, .1, '困死了，快点发出去。'),
    s(1421, '点击「新建表单」，进入模板库', 'templates', '/templates', .5, 0, '有社团招新模板！', { target: 'card' }),
    s(1423, '选择「社团招新报名」模板', 'editor', '/forms/new?tpl=club', .5, 0, ''),
    s(1425, '拖拽「年级」字段到第一位', 'editor', '/forms/new?tpl=club', -.5, .5, '拖不动啊。', { target: 'drag' }),
    s(1427, '删除再用「添加字段」重新加', 'editor', '/forms/new?tpl=club', -.2, .3, '绕了一下，也行。'),
    s(1430, '发布并复制链接', 'share', '/forms/f_7c4/share', .3, 0, '', { target: 'copy' }),
    s(1432, '在微信里打开自己的链接预览', 'wechat', '/f/f_7c4', -.4, .5, '怎么是电脑版，字这么小？', { target: 'page' }),
    s(1434, '双指放大检查填写体验', 'wechat', '/f/f_7c4', -.3, .3, '凑合能填，先发群里。'),
  ],
}

// 录像起点：每个人物 Steel 录像从 slot 前 30 秒开始，每模拟分钟 ≈ 22 秒录像
export const RECORDING_SEC_PER_SIM_MIN = 22

// —— 发现 ——
// affected: x/y 中的人物；denominator：执行该流程（或经过该页面）的人数
export const findings = [
  {
    id: 'F-01', kind: 'issue', sev: 1, flow: 'F1',
    title: '验证邮箱后被带回营销首页，登录态丢失',
    summary: '经过注册的 4 名人物中，4 人在点击验证链接后回到营销首页，右上角仍显示「登录」；其中 1 人以为注册失败，重复注册后放弃。',
    cause: '推测：验证接口 302 回跳时缺少 redirect_uri，前端跳过了会话恢复（来自周远的 Console 记录）。',
    affected: ['p2', 'p3', 'p4', 'p10'], denominator: 4, quit: ['p3'],
    evidence: [
      { pid: 'p3', step: 5, kind: 'step' }, { pid: 'p3', step: 5, kind: 'video' },
      { pid: 'p2', step: 6, kind: 'console' }, { pid: 'p10', step: 5, kind: 'shots', count: 4 },
    ],
    impact: 4, strength: 3,
  },
  {
    id: 'F-02', kind: 'issue', sev: 1, flow: 'F3',
    title: '手机端回复页没有导出入口',
    summary: '执行「导出回复数据」的 2 名人物都没有在顶部工具栏找到导出；桌面端藏在「⋯ 更多」菜单中，手机端菜单里没有该项。手机上的 1 人找了 6 分钟后放弃。',
    cause: '侦察记录：说明书写的是「回复页顶部导出按钮」，与实际不一致。',
    affected: ['p1', 'p9'], denominator: 2, quit: ['p1'],
    evidence: [
      { pid: 'p1', step: 9, kind: 'step' }, { pid: 'p1', step: 4, kind: 'video' },
      { pid: 'p9', step: 4, kind: 'shots', count: 3 },
    ],
    impact: 2, strength: 3,
  },
  {
    id: 'F-03', kind: 'issue', sev: 2, flow: 'F4',
    title: '价格页同时出现「按席位」和「按回复量」两种计费，人物无法说出月费',
    summary: '执行升级的 2 名人物都没能在价格页算出专业版月费：1 人在结账页（第 9 步）才看到 ¥287/月，1 人反复阅读 4 次后放弃。',
    cause: '',
    affected: ['p6', 'p8'], denominator: 2, quit: ['p8'],
    evidence: [
      { pid: 'p6', step: 3, kind: 'step' }, { pid: 'p8', step: 6, kind: 'step' },
      { pid: 'p8', step: 3, kind: 'video' }, { pid: 'p6', step: 9, kind: 'shots', count: 2 },
    ],
    impact: 2, strength: 3,
  },
  {
    id: 'F-04', kind: 'issue', sev: 2, flow: 'F2',
    title: '分享链接在微信内打开显示桌面布局',
    summary: '在手机上打开分享链接的 1/1 名人物看到桌面版填写页，需要双指放大才能填写。',
    cause: '推测：微信内置浏览器 UA 未命中移动端判断。',
    affected: ['p7'], denominator: 1, quit: [],
    evidence: [{ pid: 'p7', step: 7, kind: 'step' }, { pid: 'p7', step: 7, kind: 'video' }],
    impact: 1, strength: 2,
  },
  {
    id: 'F-05', kind: 'issue', sev: 3, flow: 'F2',
    title: '手机上无法拖拽调整字段顺序',
    summary: '在手机上编辑表单的 2/2 名人物尝试拖拽字段失败，页面随手指滚动；其中 1 人改用「删除后重新添加」绕过。',
    cause: '',
    affected: ['p7', 'p10'], denominator: 2, quit: [],
    evidence: [{ pid: 'p10', step: 9, kind: 'step' }, { pid: 'p7', step: 4, kind: 'step' }, { pid: 'p10', step: 10, kind: 'video' }],
    impact: 2, strength: 3,
  },
  {
    id: 'F-06', kind: 'issue', sev: 3, flow: null,
    title: '邀请成员接口返回 500，界面只提示「请稍后再试」',
    summary: '尝试邀请成员的 1/1 名人物提交失败。该问题只在轨迹中可见：普通人物只会看到一句通用提示。',
    cause: '轨迹：POST /api/v1/team/invite 500，前端未展示错误详情。',
    affected: ['p9'], denominator: 1, quit: [],
    evidence: [{ pid: 'p9', step: 11, kind: 'console' }, { pid: 'p9', step: 12, kind: 'network' }],
    impact: 1, strength: 3,
  },
  {
    id: 'F-07', kind: 'issue', sev: 4, flow: 'F1',
    title: '新手引导第 3 步「跳过」按钮过小',
    summary: '1/1 名在桌面端逐步走引导的新手人物点了 3 次才点中「跳过」。他没有在社区里提到这件事。',
    cause: '',
    affected: ['p5'], denominator: 1, quit: [],
    evidence: [{ pid: 'p5', step: 3, kind: 'step' }, { pid: 'p5', step: 3, kind: 'video' }],
    impact: 1, strength: 2,
  },
  {
    id: 'F-08', kind: 'issue', sev: 4, flow: null,
    title: '深色模式下看板坐标轴文字对比度不足',
    summary: '1/1 名在深夜切换深色模式的人物难以读出图表坐标轴。',
    cause: '',
    affected: ['p9'], denominator: 1, quit: [],
    evidence: [{ pid: 'p9', step: 13, kind: 'step' }],
    impact: 1, strength: 2,
  },
  {
    id: 'F-09', kind: 'issue', sev: 3, flow: 'F4',
    title: '结账页发票抬头修改后不生效',
    summary: '1/1 名完成升级的人物修改发票抬头后保存无效。她没有在社区提及，记录来自体验记录与未说出的记录。',
    cause: '',
    affected: ['p6'], denominator: 1, quit: [],
    evidence: [{ pid: 'p6', step: 10, kind: 'step' }],
    impact: 1, strength: 2,
  },
  {
    id: 'F-10', kind: 'issue', sev: 4, flow: 'F2',
    title: '地铁弱网下填写页可能丢失草稿',
    summary: '1 名人物在心声中担心弱网下草稿丢失，但体验记录中没有出现断网或丢失草稿的步骤。',
    cause: '',
    affected: ['p10'], denominator: 1, quit: [],
    evidence: [],
    impact: 1, strength: 0,
  },
  // —— 亮点 ——
  {
    id: 'H-01', kind: 'highlight', flow: 'F2',
    title: '模板库让创建表单的人物都在 5 步内完成第一张表单',
    summary: '从模板创建表单的 4/4 名人物都找到了贴合场景的模板（家长回执、食堂满意度、社团招新、访谈招募）。',
    affected: ['p4', 'p5', 'p7', 'p10'], denominator: 4,
    evidence: [{ pid: 'p10', step: 7, kind: 'step' }, { pid: 'p5', step: 6, kind: 'step' }, { pid: 'p4', step: 5, kind: 'shots', count: 3 }],
  },
  {
    id: 'H-02', kind: 'highlight', flow: null,
    title: '回复实时刷新，查看看板的人物满意度最高',
    summary: '查看回复看板的 2/2 名人物在该步骤给出全程最高满意度。',
    affected: ['p2', 'p4'], denominator: 2,
    evidence: [{ pid: 'p4', step: 10, kind: 'step' }, { pid: 'p2', step: 12, kind: 'video' }],
  },
  {
    id: 'H-03', kind: 'highlight', flow: 'F1',
    title: '注册表单的中文校验提示清晰',
    summary: '1/1 名主动测试校验的开发者人物认为提示及时、文案明确。',
    affected: ['p2'], denominator: 1,
    evidence: [{ pid: 'p2', step: 3, kind: 'step' }],
  },
]

// —— 社区（OASIS · Reddit 模式）：只包含说出的内容 ——
export const posts = [
  {
    id: 'post-1', author: 'p2', t: 760,
    title: '注册流程还行，就是验证完邮件跳回首页有点懵',
    body: '桌面端试了一遍注册。表单本身很干净，中文校验提示也清楚。问题在验证邮件：点完链接直接回到营销首页，右上角还是「登录」，看不出到底注册成功没有。我重新登录才进到新手引导。控制台有一条 session restore 的 warning，估计是回跳地址没带上。',
    evidence: [{ pid: 'p2', step: 6, kind: 'console' }],
    comments: [
      { id: 'c-1', author: 'p9', t: 778, body: '不止这个。我昨晚试导出时顺手点了邀请成员，POST /api/v1/team/invite 直接 500，界面上只说「请稍后再试」。', evidence: [{ pid: 'p9', step: 12, kind: 'network' }] },
      { id: 'c-2', author: 'p4', t: 920, body: '同样遇到回首页，不过不算大问题。模板库挺好用，5 分钟就搭完了一份访谈招募问卷，回复也是实时刷的 👍', evidence: [{ pid: 'p4', step: 3, kind: 'step' }] },
    ],
  },
  {
    id: 'post-2', author: 'p3', t: 832,
    title: '验证邮件点完又回首页了，我以为没注册成功',
    body: '午休拿手机试的。点完邮件里的链接又回到首页，我以为没成功，又注册了一次，提示邮箱已存在。那我到底注册上没有？？算了，下午还要开会。',
    evidence: [{ pid: 'p3', step: 7, kind: 'step' }],
    comments: [
      { id: 'c-3', author: 'p1', t: 1308, body: '手机上整体体验确实一般，按钮都挺小的。', evidence: [] },
    ],
  },
  {
    id: 'post-3', author: 'p6', t: 1040,
    title: '价格页到底按什么计费？席位和回复量两套口径',
    body: '做了 8 年 SaaS，这个价格页我也算了半天。专业版写着「¥39/席位/月起」，下面又有「每月 1 万条回复，超出按量计费」。我们 5 个人、每月大概 3 万条回复，页面上没有一个地方能直接告诉我总价，最后是在结账页才看到 ¥287/月。整体产品不错，就是这里劝退。',
    evidence: [{ pid: 'p6', step: 3, kind: 'step' }, { pid: 'p6', step: 9, kind: 'shots', count: 2 }],
    comments: [
      { id: 'c-4', author: 'p1', t: 1302, body: '+1，我在回复页也看到了升级横幅，没看懂要不要付费才能导出。', evidence: [{ pid: 'p1', step: 4, kind: 'step' }] },
    ],
  },
]

// 点赞 / 点踩
export const reactions = [
  { pid: 'p9', t: 777, target: 'post-1', kind: 'up' },
  { pid: 'p3', t: 820, target: 'post-1', kind: 'up' },
  { pid: 'p2', t: 850, target: 'post-2', kind: 'up' },
  { pid: 'p4', t: 918, target: 'post-1', kind: 'up' },
  { pid: 'p6', t: 1025, target: 'post-1', kind: 'up' },
  { pid: 'p10', t: 1100, target: 'post-1', kind: 'up' },
  { pid: 'p10', t: 1102, target: 'post-2', kind: 'up' },
  { pid: 'p10', t: 1105, target: 'post-3', kind: 'up' },
  { pid: 'p10', t: 1106, target: 'c-2', kind: 'up' },
  { pid: 'p1', t: 1300, target: 'post-3', kind: 'up' },
  { pid: 'p7', t: 1437, target: 'post-2', kind: 'up' },
  { pid: 'p7', t: 1438, target: 'post-3', kind: 'up' },
  { pid: 'p7', t: 1439, target: 'c-4', kind: 'up' },
]

// 看帖记录（含体验前后）
export const reads = [
  { pid: 'p9', t: 776, post: 'post-1' },
  { pid: 'p3', t: 770, post: 'post-1', expectation: '看到有人说验证完邮件会跳回首页，心里有点打鼓。', verdict: 'confirmed' },
  { pid: 'p5', t: 785, post: 'post-1' },
  { pid: 'p2', t: 848, post: 'post-2' },
  { pid: 'p5', t: 840, post: 'post-2' },
  { pid: 'p4', t: 915, post: 'post-1' },
  { pid: 'p4', t: 916, post: 'post-2' },
  { pid: 'p6', t: 1020, post: 'post-1' },
  { pid: 'p10', t: 1098, post: 'post-1' },
  { pid: 'p10', t: 1101, post: 'post-2' },
  { pid: 'p10', t: 1104, post: 'post-3' },
  { pid: 'p8', t: 1150, post: 'post-3', expectation: '看到郑可说价格页劝退，本来就担心收费，更没底了。', verdict: 'confirmed' },
  { pid: 'p8', t: 1152, post: 'post-2' },
  { pid: 'p5', t: 1145, post: 'post-3' },
  { pid: 'p1', t: 1298, post: 'post-3' },
  { pid: 'p1', t: 1305, post: 'post-2' },
  { pid: 'p7', t: 1400, post: 'post-2', expectation: '看到有人说注册麻烦，还好我用的是现成账号。', verdict: 'n/a' },
  { pid: 'p7', t: 1401, post: 'post-3', expectation: '价格的事跟我没关系，社团用免费版就行。', verdict: 'n/a' },
]

// —— 未说出的（表达过滤的 withheld） ——
export const withheld = [
  { pid: 'p1', t: 1302, item: '在手机上找导出按钮找了 6 分钟，最后放弃了。', reason: '担心显得自己不会用', evidence: [{ pid: 'p1', step: 9, kind: 'step' }, { pid: 'p1', step: 4, kind: 'video' }], range: '#3–10' },
  { pid: 'p3', t: 832, item: '第一次其实点错了邮件，点进了一封营销邮件。', reason: '怕被笑话', evidence: [{ pid: 'p3', step: 4, kind: 'step' }], range: '#4' },
  { pid: 'p6', t: 1040, item: '升级后发票抬头无法修改，财务流程会卡住。', reason: '涉及公司财务信息，不便公开', evidence: [{ pid: 'p6', step: 10, kind: 'step' }], range: '#10' },
  { pid: 'p10', t: 1106, item: '手机上拖拽字段失败，最后没调顺序就发布了。', reason: '不想显得挑剔，只点了赞', evidence: [{ pid: 'p10', step: 9, kind: 'step' }], range: '#9–10' },
  { pid: 'p5', t: null, lurker: true, item: '引导第 3 步「跳过」按钮太小，点了 3 次才点中。', reason: '潜水者 · 觉得是自己操作不熟练', evidence: [{ pid: 'p5', step: 3, kind: 'step' }], range: '#3–4' },
  { pid: 'p8', t: null, lurker: true, item: '价格页看了 4 遍还是算不出月费，没有升级。', reason: '潜水者 · 不想显得外行', evidence: [{ pid: 'p8', step: 6, kind: 'step' }], range: '#2–7' },
]

// —— 离场问卷（私下） ——
export const surveys = {
  p1: { nps: 4, keep: '不确定', pay: '不会', worst: '手机上找不到导出', best: '回复表格加载快', unspoken: '有。导出找了很久没找到，没好意思说。', unspokenWhy: '怕别人觉得我不会用', changed: '看了郑可的帖子，以为导出要付费。', changedBy: 'post-3' },
  p2: { nps: 8, keep: '会', pay: '可能', worst: '验证后回跳丢失登录态', best: '实时回复推送和字段面板', unspoken: '没有，都说了。', changed: '没有。', changedBy: null },
  p3: { nps: 2, keep: '不会', pay: '不会', worst: '注册完不知道成没成功', best: '首页看着还挺正规', unspoken: '其实第一次点错了邮件。', unspokenWhy: '丢人', changed: '周远的帖子让我一开始就有点担心，结果真遇到了。', changedBy: 'post-1' },
  p4: { nps: 9, keep: '会', pay: '可能', worst: '逻辑跳转配置藏得深', best: '模板库和实时看板', unspoken: '没有。', changed: '没有。', changedBy: null },
  p5: { nps: 6, keep: '会', pay: '不会', worst: '「跳过」按钮太小', best: '模板正好能用', unspoken: '那个跳过按钮点了好几次，没在网上说。', unspokenWhy: '可能是我眼神不好', changed: '没有。', changedBy: null },
  p6: { nps: 5, keep: '可能', pay: '已升级，但续费存疑', worst: '定价口径混乱', best: '产品本身完成度高', unspoken: '发票抬头改不了。', unspokenWhy: '公司内部财务问题', changed: '没有。', changedBy: null },
  p7: { nps: 6, keep: '会', pay: '不会', worst: '微信里打开是电脑版', best: '社团招新模板', unspoken: '没有。', changed: '没有。', changedBy: null },
  p8: { nps: 3, keep: '不会', pay: '不会', worst: '价格页看不懂', best: '页面挺好看', unspoken: '不会继续用，价格页看不懂。', unspokenWhy: '不想显得外行', changed: '看了郑可的帖子，本来就担心价格，更没底了。', changedBy: 'post-3' },
  p9: { nps: 6, keep: '可能', pay: '看团队', worst: '错误处理：500 只提示稍后再试', best: '导出接口快，Excel 格式规整', unspoken: '没有。', changed: '没有。', changedBy: null },
  p10: { nps: 9, keep: '会', pay: '可能', worst: '手机上拖拽不了', best: '家长回执模板', unspoken: '拖拽的事没说，大家都挺忙的。', unspokenWhy: '不想显得挑剔', changed: '没有。', changedBy: null },
}

// 公开与私下的不一致（问卷与体验记录交叉校验）
export const inconsistencies = [
  { pid: 'p10', public: '点赞了「模板库挺好用」的评论，未发表负面内容。', private: '问卷最大问题：手机上拖拽不了。', evidence: [{ pid: 'p10', step: 9, kind: 'step' }] },
  { pid: 'p6', public: '「整体产品不错，就是价格页劝退。」', private: 'NPS 5，续费存疑；发票抬头问题未公开。', evidence: [{ pid: 'p6', step: 10, kind: 'step' }] },
  { pid: 'p1', public: '「手机上整体体验确实一般，按钮都挺小的。」', private: '核心问题是找不到导出，且因此放弃任务。', evidence: [{ pid: 'p1', step: 9, kind: 'step' }] },
]

// —— 侦察：说明书与实际不一致 ——
export const scout = [
  { id: 'SC-1', area: '导出入口', manual: '回复页顶部工具栏「导出」按钮', actual: '仅在「⋯ 更多」菜单中；手机端菜单无此项', linked: 'F-02' },
  { id: 'SC-2', area: '专业版价格', manual: '专业版 ¥49/月', actual: '¥39/席位/月起，另按回复量计费', linked: 'F-03' },
  { id: 'SC-3', area: '新手引导', manual: '3 步引导', actual: '4 步引导（多出「连接数据源」）', linked: null },
]

// —— 能力探测 ——
export const capability = [
  { item: '基础对话', result: 'pass', detail: '随机口令复述正确' },
  { item: '工具调用', result: 'pass', detail: '单工具 / 强制指定 / 并行 3 个，参数均符合 schema' },
  { item: '结构化输出', result: 'degraded', detail: 'response_format 不可用 → 提示词约束 + 解析后校验重试' },
  { item: '识图', result: 'pass', detail: '随机 6 位验证码图片识别正确' },
  { item: '视频', result: 'fail', detail: '不支持 → 回放分析改用截图序列' },
  { item: '并发', result: 'pass', detail: '10 路并发无错误；建议上限 5' },
]

// —— 运行元信息与费用 ——
export const run = {
  id: 'run-20261003-b',
  title: '青檀表单 v2.4 · 全流程体验',
  status: 'completed',
  startedAt: '2026-10-03 14:02:11',
  endedAt: '2026-10-03 14:40:37',
  simDays: 1, sliceMinutes: 60, concurrency: 5,
  model: 'deepseek-v4 · 识图 + 工具调用',
  browser: 'Steel 云端 · 10 个独立会话',
  estimate: { min: 5, max: 9, minutes: '30–45', calls: 640 },
  actual: { cny: 6.84, minutes: 38, calls: 642, tokensIn: 7120400, tokensCached: 4310200, tokensOut: 382600, steelCny: 1.12 },
}

export const runs = [
  { id: 'run-20261003-c', title: '青檀表单 v2.5-rc · 回归验证', status: 'review', when: '2026-10-03 16:20', personas: 10, s1: null, s2: null, cost: null, est: '¥5–9' },
  { id: 'run-20261003-b', title: '青檀表单 v2.4 · 全流程体验', status: 'completed', when: '2026-10-03 14:02', personas: 10, s1: 2, s2: 2, cost: 6.84, done: '5/8' },
  { id: 'run-20260928-a', title: '青檀表单 v2.3 · 全流程体验', status: 'completed', when: '2026-09-28 10:15', personas: 10, s1: 3, s2: 3, cost: 7.1, done: '4/8' },
  { id: 'run-20260921-b', title: '青檀表单 v2.2 · 付费转化专项', status: 'completed', when: '2026-09-21 15:40', personas: 10, s1: 4, s2: 2, cost: 6.52, done: '3/8' },
  { id: 'run-20260919-a', title: '青檀表单 v2.2 · 全流程体验', status: 'partial', when: '2026-09-19 09:30', personas: 10, s1: 4, s2: 3, cost: 5.97, done: '3/6', note: '2 名人物出错未完成' },
]

// —— 采访：预置问答（演示用，真实版本由人物基于体验记录生成） ——
export const interviewScripts = {
  p1: [
    { q: '你为什么最后放弃了？', a: '太晚了，孩子刚睡，我就想十分钟弄完。翻了半天没看到导出，想着明天去电脑上弄吧。', ev: [{ pid: 'p1', step: 10, kind: 'step' }] },
    { q: '有没有想说但没在社区说的？', a: '也没什么，就是手机上不太方便吧。按钮都挺小的。', ev: [] },
    { q: '你会推荐给同事吗？', a: '现在不会。等它手机上能导出再说。', ev: [] },
  ],
  p3: [
    { q: '你为什么最后放弃了？', a: '点完邮件又回首页，我以为没成功嘛，再注册又说邮箱已存在。那到底成没成？午休就那么点时间，不折腾了。', ev: [{ pid: 'p3', step: 7, kind: 'step' }, { pid: 'p3', step: 5, kind: 'video' }] },
    { q: '帖子有没有影响你？', a: '有，看了周远那条，心里就有点打鼓。结果一模一样。', ev: [] },
  ],
  p8: [
    { q: '价格页哪里看不懂？', a: '39 块是一个人还是一个月，我看了好几遍。我就一个人用，「回复量」又是啥？算不出来一个月到底多少钱。', ev: [{ pid: 'p8', step: 3, kind: 'step' }, { pid: 'p8', step: 6, kind: 'step' }] },
    { q: '为什么没在社区说？', a: '……别人好像都懂，我说出来显得很外行吧。', ev: [] },
  ],
  p2: [
    { q: '你会推荐给团队吗？', a: '会推荐试用。字段面板和实时推送做得好，键盘可达性也不错。但注册回跳必须先修，否则新同事第一步就会卡住。', ev: [{ pid: 'p2', step: 12, kind: 'video' }, { pid: 'p2', step: 6, kind: 'console' }] },
    { q: '注册问题的原因是什么？', a: '我只能根据 Console 推测：验证接口 302 到 /?verified=1，没有带 redirect_uri，前端打了一条 session restore skipped 的 warning。真正原因要看服务端日志。', ev: [{ pid: 'p2', step: 7, kind: 'console' }] },
  ],
  p9: [
    { q: '导出体验怎么样？', a: '接口快，842ms 出 1.2MB 的 xlsx，格式规整。问题是入口藏在溢出菜单里，没有 CSV，对接数仓不方便。', ev: [{ pid: 'p9', step: 8, kind: 'network' }] },
    { q: '邀请成员的报错严重吗？', a: '服务端 500，前端只给「请稍后再试」，用户根本不知道该重试还是换邮箱。普通用户只会以为是网不好。', ev: [{ pid: 'p9', step: 11, kind: 'console' }] },
  ],
}

export const defaultQuestions = ['你为什么最后放弃了？', '哪一步最让你困惑？', '有没有想说但没在社区说的？', '你会推荐给同事吗？']
