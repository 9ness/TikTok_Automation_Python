# (Alternativa a la página «Navegador remoto» de Ajustes, que no necesita terminal ni túnel.)
# Abre el navegador del VPS (Chrome con pantalla virtual) en tu navegador del PC.
#   1) enciende el Chrome del VPS (`navegador on`), 2) abre el túnel SSH, 3) abre noVNC.
# La contraseña de la pantalla está en el VPS, solo para root:
#   ssh root@62.238.19.31 "cat /root/navegador_vnc_password.txt"
# Al terminar de trabajar: `ssh root@62.238.19.31 navegador off` (libera ~1-2 GB de RAM).
$vps = "root@62.238.19.31"
ssh $vps "navegador on" | Out-Null
$tunel = Start-Process ssh -ArgumentList "-N","-L","6080:172.18.0.1:6080",$vps -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3
Start-Process "http://localhost:6080/vnc.html?autoconnect=1&resize=remote"
Write-Host "Túnel abierto (pid $($tunel.Id)). Pulsa Enter para cerrarlo y apagar el navegador del VPS."
Read-Host | Out-Null
Stop-Process -Id $tunel.Id -ErrorAction SilentlyContinue
ssh $vps "navegador off"
