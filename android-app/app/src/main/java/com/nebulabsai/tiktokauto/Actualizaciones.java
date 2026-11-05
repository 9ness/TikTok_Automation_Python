package com.nebulabsai.tiktokauto;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.provider.Settings;
import android.view.View;
import android.widget.RemoteViews;
import android.widget.Toast;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Avisa cuando hay una versión nueva de la app y la instala SIN SALIR de ella.
 *
 * Cómo sabe si hay una nueva: la release fija `apk-latest` lleva en su
 * descripción una línea `versionCode=N` que escribe el propio workflow. Se
 * compara con la que trae esta APK.
 *
 * Hasta la 3.3 la notificación abría la descarga en el NAVEGADOR: había que
 * esperar, ir a descargas y tocar el fichero. Ahora, al tocarla, la app baja
 * la APK a su caché (con barra de progreso en la notificación) y le pasa el
 * fichero al instalador de Android, que solo pregunta «¿Quieres actualizar?».
 *
 * La primera vez Android pide además el permiso «Instalar apps desconocidas»
 * para ESTA app (es por app y no se puede saltar): se abre esa pantalla, se
 * activa, se vuelve y la actualización sigue sola (`alVolver`).
 *
 * Si no hay red, o GitHub no contesta, no pasa nada: no se avisa y punto. Esto
 * NUNCA puede impedir usar la app. Y si la instalación falla, queda el plan B
 * de siempre: abrir la descarga en el navegador.
 */
final class Actualizaciones {

    private static final String API =
        "https://api.github.com/repos/9ness/TikTok_Automation_Python/releases/tags/apk-latest";
    static final String DESCARGA =
        "https://github.com/9ness/TikTok_Automation_Python/releases/download/apk-latest/tiktok-auto.apk";

    /** La notificación pide a la pantalla que actualice. */
    static final String ACCION_ACTUALIZAR = "com.nebulabsai.tiktokauto.ACTUALIZAR";
    /** El instalador de Android devuelve aquí cómo ha ido. */
    static final String ACCION_ESTADO = "com.nebulabsai.tiktokauto.ESTADO_INSTALACION";

    private static final String CANAL = "actualizaciones";
    private static final int ID_AVISO = 3001;
    private static final String FICHERO = "actualizacion.apk";

    /** Una sola descarga a la vez: tocar dos veces no baja dos APK. */
    private static volatile boolean bajando = false;
    /** Se fue a dar el permiso de instalar: al volver hay que seguir. */
    private static volatile boolean esperandoPermiso = false;

    private Actualizaciones() {}

    // ------------------------------------------------------------------ aviso

    /** Mira si hay versión nueva. Va en su propio hilo: es red. */
    static void comprobar(Context ctx) {
        new Thread(() -> {
            try {
                if (versionPublicada() > BuildConfig.VERSION_CODE) {
                    notificar(ctx, "Hay una versión nueva", "Toca para actualizar", -1);
                }
            } catch (Throwable ignorada) {
                // Sin red o GitHub caído: no se avisa y ya está.
            }
        }).start();
    }

    private static int versionPublicada() throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(API).openConnection();
        con.setConnectTimeout(8000);
        con.setReadTimeout(8000);
        con.setRequestProperty("Accept", "application/vnd.github+json");
        try (InputStream in = con.getInputStream()) {
            // Nada de `readAllBytes`: es API 33 y aquí el mínimo es 29.
            java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
            byte[] trozo = new byte[8192];
            int leidos;
            while ((leidos = in.read(trozo)) != -1) buf.write(trozo, 0, leidos);
            org.json.JSONObject release = new org.json.JSONObject(buf.toString("UTF-8"));
            String notas = release.optString("body", "");
            java.util.regex.Matcher m =
                java.util.regex.Pattern.compile("versionCode\\s*=\\s*(\\d+)").matcher(notas);
            return m.find() ? Integer.parseInt(m.group(1)) : 0;
        } finally {
            con.disconnect();
        }
    }

    /**
     * La notificación de la actualización. `pct` < 0 = sin barra.
     * Tocarla abre la app con `ACCION_ACTUALIZAR` (no el navegador).
     */
    private static void notificar(Context ctx, String titulo, String detalle, int pct) {
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        NotificationChannel canal = new NotificationChannel(
            CANAL, "Actualizaciones", NotificationManager.IMPORTANCE_DEFAULT);
        canal.setDescription("Cuando hay una versión nueva de la app");
        nm.createNotificationChannel(canal);

        RemoteViews vista = new RemoteViews(ctx.getPackageName(), R.layout.aviso_descargas);
        vista.setTextViewText(R.id.titulo, titulo);
        vista.setTextViewText(R.id.detalle, detalle);
        vista.setViewVisibility(R.id.cifras, View.GONE);
        if (pct >= 0) {
            vista.setViewVisibility(R.id.barra, View.VISIBLE);
            vista.setProgressBar(R.id.barra, 100, pct, false);
        } else {
            vista.setViewVisibility(R.id.barra, View.GONE);
        }

        Intent abrir = new Intent(ctx, MainActivity.class).setAction(ACCION_ACTUALIZAR);
        PendingIntent alTocar = PendingIntent.getActivity(
            ctx, 0, abrir, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);

        boolean enCurso = pct >= 0;
        nm.notify(ID_AVISO, new Notification.Builder(ctx, CANAL)
            .setSmallIcon(R.drawable.ic_descarga)
            .setColor(0xFF15DBF9)
            .setStyle(new Notification.DecoratedCustomViewStyle())
            .setCustomContentView(vista)
            .setContentIntent(alTocar)
            .setOnlyAlertOnce(true)
            .setOngoing(enCurso)
            .setAutoCancel(!enCurso)
            .build());
    }

    private static void quitarAviso(Context ctx) {
        ctx.getSystemService(NotificationManager.class).cancel(ID_AVISO);
    }

    // ------------------------------------------------------------- actualizar

    /** Lo que hace tocar la notificación: permiso → descarga → instalador. */
    static void actualizar(Activity act) {
        if (!act.getPackageManager().canRequestPackageInstalls()) {
            esperandoPermiso = true;
            Toast.makeText(act,
                "Activa «Permitir de esta fuente» y vuelve atrás: la actualización sigue sola",
                Toast.LENGTH_LONG).show();
            try {
                act.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + act.getPackageName())));
            } catch (Exception sinPantalla) {
                esperandoPermiso = false;
                abrirEnNavegador(act);
            }
            return;
        }

        File apk = new File(act.getCacheDir(), FICHERO);
        if (apkValida(act, apk)) {
            instalar(act, apk);
            return;
        }
        if (bajando) {
            Toast.makeText(act, "Ya se está descargando la actualización", Toast.LENGTH_SHORT).show();
            return;
        }
        bajando = true;
        Context app = act.getApplicationContext();
        new Thread(() -> {
            try {
                bajar(app, apk);
                if (!apkValida(app, apk)) throw new Exception("La APK descargada no es válida");
                act.runOnUiThread(() -> {
                    // Si se salió de la app mientras bajaba, Android no deja
                    // abrir el instalador desde segundo plano: se deja avisado
                    // y al tocar se instala ya sin volver a bajar.
                    if (act.isFinishing() || !act.hasWindowFocus()) {
                        notificar(app, "Actualización descargada", "Toca para instalarla", -1);
                    } else {
                        instalar(act, apk);
                    }
                });
            } catch (Throwable e) {
                apk.delete();
                notificar(app, "No se pudo descargar la actualización", "Toca para reintentar", -1);
            } finally {
                bajando = false;
            }
        }).start();
    }

    /** Al volver de los ajustes del permiso (lo llama `onResume`). */
    static void alVolver(Activity act) {
        if (!esperandoPermiso) return;
        esperandoPermiso = false;
        if (act.getPackageManager().canRequestPackageInstalls()) actualizar(act);
        else Toast.makeText(act, "Sin ese permiso no se puede actualizar desde la app",
            Toast.LENGTH_LONG).show();
    }

    private static void bajar(Context ctx, File destino) throws Exception {
        File parcial = new File(destino.getPath() + ".part");
        // GitHub redirige a otro dominio (objects.githubusercontent.com), los
        // dos https: HttpURLConnection sigue esa redirección solo.
        HttpURLConnection con = (HttpURLConnection) new URL(DESCARGA).openConnection();
        con.setConnectTimeout(15000);
        con.setReadTimeout(30000);
        con.setInstanceFollowRedirects(true);
        try (InputStream in = con.getInputStream();
             OutputStream out = new FileOutputStream(parcial)) {
            long total = con.getContentLengthLong();
            long hecho = 0;
            int ultimo = -1;
            byte[] trozo = new byte[64 * 1024];
            int leidos;
            notificar(ctx, "Descargando actualización", "Un momento…", 0);
            while ((leidos = in.read(trozo)) != -1) {
                out.write(trozo, 0, leidos);
                hecho += leidos;
                if (total > 0) {
                    int pct = (int) (hecho * 100 / total);
                    if (pct != ultimo) {
                        ultimo = pct;
                        notificar(ctx, "Descargando actualización",
                            String.format(java.util.Locale.ROOT, "%.1f de %.1f MB",
                                hecho / 1048576f, total / 1048576f), pct);
                    }
                }
            }
        } finally {
            con.disconnect();
        }
        if (!parcial.renameTo(destino)) throw new Exception("No se pudo guardar la APK");
    }

    /** Es nuestra app y es MÁS nueva que la instalada (si no, se vuelve a bajar). */
    private static boolean apkValida(Context ctx, File apk) {
        if (!apk.isFile()) return false;
        PackageInfo info = ctx.getPackageManager().getPackageArchiveInfo(apk.getPath(), 0);
        boolean vale = info != null
            && ctx.getPackageName().equals(info.packageName)
            && info.getLongVersionCode() > BuildConfig.VERSION_CODE;
        if (!vale) apk.delete();
        return vale;
    }

    /**
     * Pasa la APK al instalador del sistema. Android responde con
     * `STATUS_PENDING_USER_ACTION` y la pantalla de «¿Actualizar?», que se abre
     * en `resultado`. Si sale bien, Android cierra esta app y la reemplaza.
     */
    private static void instalar(Activity act, File apk) {
        quitarAviso(act);
        try {
            PackageInstaller pi = act.getPackageManager().getPackageInstaller();
            PackageInstaller.SessionParams params =
                new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
            params.setAppPackageName(act.getPackageName());
            params.setSize(apk.length());
            int id = pi.createSession(params);
            try (PackageInstaller.Session sesion = pi.openSession(id)) {
                try (InputStream in = new FileInputStream(apk);
                     OutputStream out = sesion.openWrite("app.apk", 0, apk.length())) {
                    byte[] trozo = new byte[64 * 1024];
                    int leidos;
                    while ((leidos = in.read(trozo)) != -1) out.write(trozo, 0, leidos);
                    sesion.fsync(out);
                }
                // MUTABLE a la fuerza: el instalador mete aquí el estado.
                Intent estado = new Intent(act, MainActivity.class).setAction(ACCION_ESTADO);
                PendingIntent pend = PendingIntent.getActivity(act, id, estado,
                    PendingIntent.FLAG_MUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
                sesion.commit(pend.getIntentSender());
            }
        } catch (Exception e) {
            fallo(act, apk, String.valueOf(e.getMessage()));
        }
    }

    /** La respuesta del instalador (llega a `onNewIntent` con `ACCION_ESTADO`). */
    static void resultado(Activity act, Intent intent) {
        int estado = intent.getIntExtra(PackageInstaller.EXTRA_STATUS,
            PackageInstaller.STATUS_FAILURE);
        File apk = new File(act.getCacheDir(), FICHERO);
        if (estado == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirmar = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirmar != null) {
                try {
                    act.startActivity(confirmar);
                    return;
                } catch (Exception e) {
                    fallo(act, apk, String.valueOf(e.getMessage()));
                    return;
                }
            }
        }
        if (estado == PackageInstaller.STATUS_SUCCESS) {
            apk.delete();
            return;
        }
        if (estado == PackageInstaller.STATUS_FAILURE_ABORTED) {
            // Ha pulsado «Cancelar»: se deja la APK para no volver a bajarla.
            notificar(act, "Actualización sin instalar", "Toca para instalarla", -1);
            return;
        }
        fallo(act, apk, intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE));
    }

    private static void fallo(Activity act, File apk, String motivo) {
        apk.delete();
        Toast.makeText(act, "No se pudo instalar (" + motivo + "). Se abre la descarga.",
            Toast.LENGTH_LONG).show();
        abrirEnNavegador(act);
    }

    private static void abrirEnNavegador(Context ctx) {
        try {
            ctx.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(DESCARGA))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (Exception ignorada) {
            // Ni navegador: no hay más que hacer.
        }
    }
}
