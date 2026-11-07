"""Stable download categories. Raw exception/URL/cookie strings never leave worker."""
import re
ERRORS={
 'VIDEO_DEPENDENCY':'下载组件缺失；运行 INSTALL_ALL.bat 补齐后重启服务',
 'VIDEO_SOURCE_UNAVAILABLE':'来源解析或访问失败，原因未确定；不能仅凭此提示认定需要登录',
 'VIDEO_LIVE':'只缓存已发布的点播视频，不下载直播或预约视频',
 'VIDEO_SPACE':'磁盘空间不足或达到缓存容量限制；未到期视频保留',
 'VIDEO_SIZE':'本视频超过4 GiB限制，未完成文件不会作为缓存发布',
 'VIDEO_TIMEOUT':'下载超过本轮2小时上限；已停止，笔记保留',
 'VIDEO_OUTPUT':'没有得到完整且受支持的视频文件；不会把部分文件当成功',
 'VIDEO_RUNTIME':'缺少受支持的JavaScript运行时；用 INSTALL_ALL.bat 检查Deno/Node后重启服务',
 'VIDEO_EJS':'YouTube解析脚本缺失或挑战解析失败；更新本项目yt-dlp[default]及运行时后重试',
 'VIDEO_FFMPEG':'合并音视频失败或缺少FFmpeg；检查FFmpeg/ffprobe后重启服务',
 'VIDEO_HTTP_403':'媒体请求被拒绝(403)；可能是临时链接、平台验证或会话限制，已登录也不保证可下载',
 'VIDEO_HTTP_429':'平台限制请求频率(429)；请停止重复重试，稍后再试',
 'VIDEO_NETWORK':'网络连接、DNS或请求等待失败；检查本地网络/代理，不要反复登录',
 'VIDEO_TLS':'HTTPS证书验证失败；检查网络/系统证书，不会关闭TLS检查',
 'VIDEO_NO_FORMATS':'没有满足最高720p要求的可下载格式；检查下载组件和FFmpeg，登录并非唯一原因',
 'VIDEO_LOGIN_REQUIRED':'来源要求登录或会话验证；可在缓存页主动授权本次使用YouTube登录状态',
 'VIDEO_LOGIN_EXPIRED':'YouTube会话已失效；重新登录后手动授权本次重试',
 'VIDEO_AUTH_EMPTY':'本次未取得可用的YouTube登录会话',
 'VIDEO_AUTH_EXPIRED':'本次授权在队列中已超时；未使用旧凭据，请重新主动授权',
 'VIDEO_AUTH_CONSENT':'未获得本次登录状态使用许可',
 'VIDEO_AUTH_SCOPE':'登录数据不属于允许的YouTube范围',
 'VIDEO_AUTH_FORMAT':'登录数据格式不符合要求',
 'VIDEO_AUTH_SIZE':'登录数据超过安全传输上限',
 'VIDEO_PROTECTED':'来源含DRM或受保护格式，本工具不处理',
 'VIDEO_RESTRICTED':'来源为付费、会员或私有访问内容，本工具不处理',
 'VIDEO_LIMIT_SIGNAL':'下载组件返回数量限额结束信号；不是来源拒绝或登录失败',
 'VIDEO_WORKER':'下载工作进程失败，未取得更具体分类；原文和已有缓存保留',
}
def error_code(exc):
    text=str(exc).lower()
    explicit=re.search(r'\bvideo_[a-z_0-9]+\b',text)
    if explicit and explicit.group().upper() in ERRORS:return explicit.group().upper()
    if type(exc).__name__=='MaxDownloadsReached':return 'VIDEO_LIMIT_SIGNAL'
    for tokens,code in [
        (('cookies are no longer valid','cookies have expired'),'VIDEO_LOGIN_EXPIRED'),
        (('sign in to confirm','login required','requires authentication','log in to','sign in to'),'VIDEO_LOGIN_REQUIRED'),
        (('drm protected','drm-protected'),'VIDEO_PROTECTED'),
        (('http error 429','too many requests'),'VIDEO_HTTP_429'),
        (('http error 403','403 forbidden'),'VIDEO_HTTP_403'),
        (('certificate verify failed','ssl: certificate'),'VIDEO_TLS'),
        (('timed out','timeout','connection reset','getaddrinfo failed','name resolution','unable to connect'),'VIDEO_NETWORK'),
        (('javascript runtime','js runtime'),'VIDEO_RUNTIME'),
        (('yt-dlp-ejs','challenge solving failed','n challenge','signature extraction failed'),'VIDEO_EJS'),
        (('requested format is not available','no video formats','only images are available'),'VIDEO_NO_FORMATS'),
        (('ffmpeg','ffprobe'),'VIDEO_FFMPEG'),
        (('larger than max-filesize',),'VIDEO_SIZE'),
    ]:
        if any(x in text for x in tokens):return code
    return 'VIDEO_SOURCE_UNAVAILABLE'
