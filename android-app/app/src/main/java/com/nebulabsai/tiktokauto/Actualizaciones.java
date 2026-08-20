package com.nebulabsai.tiktokauto;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.view.View;
import android.widget.RemoteViews;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Avisa cuando hay una versión nueva de la app.
 *
 * Hace falta ahora y no antes: la app era una TWA —una carcasa que abría la
 * web— y no se tocaba casi nunca, así que cada despliegue llegaba solo. Ahora
 * la app trae cosas propias (descargas a su carpeta, subida en segundo plano,
 * notificaciones), y eso sí se actualiza con una APK nueva. Sin aviso, el
 * operador se quedaría con una versión vieja sin enterarse.
 *
 * Cómo sabe si hay una nueva: la release fija `apk-latest` lleva en su
 * descripción una línea `versionCode=N` que escribe el propio workflow. Se
 * compara con la que trae esta APK. Nada de servidores extra ni de versiones
 * escritas a mano en dos sitios.
 *
 * Si no hay red, o GitHub no contesta, no pasa nada: no se avisa y punto. Esto
 * NUNCA puede impedir usar la app.
 */
final class Actualizaciones {

    private static final String API =
        "https://api.github.com/repos/9ness/TikTok_Automation_Python/releases/tags/apk-latest";
    static final String DESCARGA =
        "https://github.com/9ness/TikTok_Automation_Python/releases/download/apk-latest/tiktok-auto.apk";

    private static final String CANAL = "actualizaciones";
    private static final int ID_AVISO = 3001;

    private Actualizaciones() {}

    /** Mira si hay versión nueva. Va en su propio hilo: es red. */
    static void comprobar(Context ctx) {
        new Thread(() -> {
            try {
                int publicada = versionPublicada();
                if (publicada > BuildConfig.VERSION_CODE) {
                    avisar(ctx);
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

    private static void avisar(Context ctx) {
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        NotificationChannel canal = new NotificationChannel(
            CANAL, "Actualizaciones", NotificationManager.IMPORTANCE_DEFAULT);
        canal.setDescription("Cuando hay una versión nueva de la app");
        nm.createNotificationChannel(canal);

        RemoteViews vista = new RemoteViews(ctx.getPackageName(), R.layout.aviso_descargas);
        vista.setTextViewText(R.id.titulo, "Hay una versión nueva");
        vista.setTextViewText(R.id.detalle, "Toca para descargarla e instalarla");
        vista.setViewVisibility(R.id.barra, View.GONE);
        vista.setViewVisibility(R.id.cifras, View.GONE);

        // Abre la descarga en el navegador: instalar una APK desde dentro
        // pediría el permiso de "instalar apps desconocidas" y una pantalla
        // más; bajarla y tocarla es lo que ya sabe hacer el operador.
        PendingIntent abrir = PendingIntent.getActivity(
            ctx, 0, new Intent(Intent.ACTION_VIEW, Uri.parse(DESCARGA)),
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);

        nm.notify(ID_AVISO, new Notification.Builder(ctx, CANAL)
            .setSmallIcon(R.drawable.ic_descarga)
            .setColor(0xFF15DBF9)
            .setStyle(new Notification.DecoratedCustomViewStyle())
            .setCustomContentView(vista)
            .setContentIntent(abrir)
            .setAutoCancel(true)
            .build());
    }
}
