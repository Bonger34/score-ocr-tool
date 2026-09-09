param([int]$Port=18010,[string]$Page='')
# Minimal static file server (no admin rights needed) for the offline OCR tool.
# Chrome/Edge block workers and blob: resources on file:// pages, so we serve
# the html over http://127.0.0.1:<Port> to get full pdf.js/Tesseract support.
$ErrorActionPreference='Stop'
$root=(Get-Location).Path
if($Page -eq ''){
  # 取目录里最大的 .html——成品约 44 MB，同目录的 readme.html 之类不会被误选
  $f0=Get-ChildItem -Path $root -Filter '*.html' | Sort-Object Length -Descending | Select-Object -First 1
  if($f0 -ne $null){ $Page=$f0.Name }
}
if($Page -eq '' -or $Page -eq $null){
  Write-Host '[ERROR] No tool html found in current folder.'
  exit 1
}
$l=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$Port)
$l.Start()
Write-Host ('Serving  http://127.0.0.1:{0}/{1}' -f $Port,$Page)
Write-Host 'The server runs in THIS window. Close this window (or press Ctrl+C) to stop it.'
Write-Host '关掉本窗口即停止服务；已经打开的页面不受影响。'
# v2.2：优先用带 --force_high_performance_gpu 的 Chrome/Edge 打开——双显卡笔记本上
# 浏览器默认把 GPU 进程放在核显上，WebGPU 会跟着跑核显，识别速度慢数倍且更易驱动异常。
try{
  $url='http://127.0.0.1:{0}/{1}' -f $Port,$Page
  $cands=@(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
  )
  $br=$cands | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if($br){ Start-Process -FilePath $br -ArgumentList '--force_high_performance_gpu',$url }
  else { Start-Process $url }
}catch{}
while($true){
  $c=$l.AcceptTcpClient()
  $s=$c.GetStream()
  try{
    # 5 秒读超时：浏览器可能先开一条空闲连接(preconnect)却不发请求，
    # 单线程服务器没有超时就会被它卡死，后面的页面请求永远等不到响应。
    $s.ReadTimeout=5000
    $rd=New-Object IO.StreamReader($s)
    $line=$rd.ReadLine()
    if($line){
      $path=($line -split ' ')[1]
      if($path -eq '/' -or $path -eq ''){ $path='/'+$Page }
      $path=[uri]::UnescapeDataString($path)
      $f=$root+$path.Replace('/','\')
      if(Test-Path -LiteralPath $f){
        $b=[IO.File]::ReadAllBytes($f)
        $ct='application/octet-stream'
        if($f -like '*.html'){ $ct='text/html; charset=utf-8' }
        $hdr="HTTP/1.1 200 OK`r`nContent-Type: $ct`r`nContent-Length: $($b.Length)`r`nConnection: close`r`n`r`n"
        $hb=[Text.Encoding]::ASCII.GetBytes($hdr)
        $s.Write($hb,0,$hb.Length)
        $s.Write($b,0,$b.Length)
      } else {
        $hdr="HTTP/1.1 404 Not Found`r`nContent-Length: 0`r`nConnection: close`r`n`r`n"
        $hb=[Text.Encoding]::ASCII.GetBytes($hdr)
        $s.Write($hb,0,$hb.Length)
      }
    }
  } catch { }
  finally {
    try{ $s.Close() }catch{}
    try{ $c.Close() }catch{}
  }
}
