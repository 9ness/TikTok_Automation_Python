package com.nebulabsai.tiktokauto;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.IBinder;
import android.os.PowerManager;
import android.provider.OpenableColumns;
import android.view.View;
import android.widget.RemoteViews;

import java.io.DataOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;

/**
 * Sube los vídeos en SEGUNDO PLANO, de verdad.
 *
 * Por qué un servicio y no la web: hoy la app usa Background Fetch, que lo
 * gestiona Chrome y lo corta cuando le parece — de ahí que "a veces no se
 * suben". Un servicio en primer plano (con su notificación) no lo mata Android
 * mientras la notificación siga puesta, así que la tanda llega entera aunque se
 * bloquee el móvil o se salga de la app.
 *
 * Lo que hace y lo que NO: sube los ficheros y devuelve lo que conteste el
 * servidor. El reparto y la confirmación siguen en la web, que es donde está
 * esa lógica; aquí solo se mueve la parte pesada.
 *
 * Los bytes van en STREAMING desde el `content://` del fichero. Nada de leerlo
 * entero en memoria: son vídeos de 20-30 MB y con diez a la vez no cabrían.
 */
public class ServicioSubidas extends Service {

    /** Las tareas, en JSON: `[{"uri":…,"nombre":…,"url":…,"campos":{…}}]`.
     *
     *  Una lista de tareas y no "una tanda con campos comunes" porque los dos
     *  sitios que suben mandan cosas distintas: la tanda va a `video/upload`
     *  con `source`+`folder`, y cada clip a `clip/upload` con su producto, su
     *  hueco y las herramientas de ESA tarjeta. */
    static final String EXTRA_TAREAS = "tareas";
    static final String EXTRA_API_KEY = "apiKey";
    static final String EXTRA_COOKIE = "cookie";

    /** Dónde se dejan las respuestas hasta que la pantalla vuelva a estar viva. */
    static final String PREFS = "subidas";
    static final String CLAVE_RESULTADOS = "resultados";

    private static final String CANAL = "subidas";
    private static final int ID_AVISO = 2001;

    private Thread hilo;

    @Override
    public IBinder onBind(Intent i) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel canal = new NotificationChannel(
            CANAL, "Subidas", NotificationManager.IMPORTANCE_LOW);
        canal.setDescription("Vídeos que se están subiendo");
        nm.createNotificationChannel(canal);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) {
            stopSelf();
            return START_NOT_STICKY;
        }
        String tareasJson = intent.getStringExtra(EXTRA_TAREAS);
        String apiKey = intent.getStringExtra(EXTRA_API_KEY);
        String cookie = intent.getStringExtra(EXTRA_COOKIE);

        org.json.JSONArray tareas;
        try {
            tareas = new org.json.JSONArray(tareasJson == null ? "[]" : tareasJson);
        } catch (Exception e) {
            stopSelf();
            return START_NOT_STICKY;
        }

        // La notificación tiene que estar ANTES de empezar: es lo que convierte
        // esto en un servicio en primer plano y lo que impide que Android lo
        // mate al salir de la app.
        startForeground(ID_AVISO, aviso(0, tareas.length(), "", 0));

        final org.json.JSONArray lista = tareas;
        hilo = new Thread(() -> trabajar(lista, apiKey, cookie));
        hilo.start();
        // START_NOT_STICKY: si el sistema lo matara igualmente, no se reintenta
        // solo — repetir una subida a medias duplicaría vídeos en la carpeta.
        return START_NOT_STICKY;
    }

    private void trabajar(org.json.JSONArray tareas, String apiKey, String cookie) {
        // Mantiene la CPU despierta con la pantalla apagada. Sin esto, el móvil
        // se duerme a mitad de una subida larga y la conexión se corta.
        PowerManager pm = getSystemService(PowerManager.class);
        PowerManager.WakeLock candado = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK, "ttshop:subidas");
        candado.acquire(30 * 60 * 1000L);

        StringBuilder resultados = new StringBuilder("[");
        int total = tareas.length();
        try {
            for (int i = 0; i < total; i++) {
                org.json.JSONObject t = tareas.getJSONObject(i);
                Uri uri = Uri.parse(t.getString("uri"));
                String nombre = t.optString("nombre", nombreDe(uri));
                notificar(aviso(i, total, nombre, 0));
                String respuesta = subirUno(
                    uri, nombre, t.getString("url"), apiKey, cookie,
                    t.optJSONObject("campos"), i, total);
                if (resultados.length() > 1) resultados.append(",");
                resultados.append(respuesta);
                // Se avisa fichero a fichero: la pantalla marca ese hueco como
                // subido sin esperar a que acabe toda la tanda.
                Avisador.subido(this, nombre, respuesta);
                notificar(aviso(i + 1, total, nombre, 100));
            }
        } catch (Throwable e) {
            // Se guarda lo que se haya conseguido: media tanda subida es mejor
            // que perderlo todo por el último fichero.
            android.util.Log.e("TikTokAuto", "falló la tanda", e);
        } finally {
            resultados.append("]");
            getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString(CLAVE_RESULTADOS, resultados.toString()).apply();
            if (candado.isHeld()) candado.release();
            stopForeground(STOP_FOREGROUND_REMOVE);
            avisoFinal(total);
            stopSelf();
        }
    }

    /** Cuánto pesa lo que hay detrás de un `content://`, o -1 si no se sabe. */
    private long tamanoDe(ContentResolver cr, Uri uri) {
        try (android.os.ParcelFileDescriptor fd = cr.openFileDescriptor(uri, "r")) {
            return fd == null ? -1 : fd.getStatSize();
        } catch (Exception e) {
            return -1;
        }
    }

    /** Un fichero, en multipart, leyendo del `content://` sin cargarlo en RAM. */
    private String subirUno(Uri uri, String nombre, String url, String apiKey,
                            String cookie, org.json.JSONObject campos,
                            int indice, int total)
            throws Exception {
        String limite = "----ttshop" + System.nanoTime();
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setDoOutput(true);
        con.setRequestMethod("POST");
        con.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + limite);
        if (apiKey != null && !apiKey.isEmpty()) con.setRequestProperty("X-API-Key", apiKey);
        if (cookie != null && !cookie.isEmpty()) con.setRequestProperty("Cookie", cookie);
        // Sin esto Android intentaría tener el cuerpo entero en memoria.
        con.setChunkedStreamingMode(256 * 1024);

        try (DataOutputStream out = new DataOutputStream(con.getOutputStream())) {
            if (campos != null) {
                java.util.Iterator<String> claves = campos.keys();
                while (claves.hasNext()) {
                    String k = claves.next();
                    campo(out, limite, k, campos.optString(k, ""));
                }
            }
            out.writeBytes("--" + limite + "\r\n");
            out.writeBytes("Content-Disposition: form-data; name=\"file\"; filename=\""
                + nombre + "\"\r\n");
            out.writeBytes("Content-Type: video/mp4\r\n\r\n");

            ContentResolver cr = getContentResolver();
            // El tamaño hace falta para el porcentaje. Si no se puede saber
            // (algún proveedor no lo da), se sube igual y solo se queda sin
            // porcentaje: no es motivo para no subir.
            long tamano = tamanoDe(cr, uri);
            try (InputStream in = cr.openInputStream(uri)) {
                byte[] buf = new byte[128 * 1024];
                int leidos;
                long enviados = 0;
                int ultimoPct = -1;
                while (in != null && (leidos = in.read(buf)) != -1) {
                    out.write(buf, 0, leidos);
                    enviados += leidos;
                    if (tamano <= 0) continue;
                    // Solo al cambiar de entero: cada trozo son 128 KB y en un
                    // vídeo de 30 MB serían 240 saltos al WebView para pintar
                    // el mismo número.
                    int pct = (int) Math.min(99, enviados * 100 / tamano);
                    if (pct != ultimoPct) {
                        ultimoPct = pct;
                        Avisador.avanza(nombre, pct);
                        notificar(aviso(indice, total, nombre, pct));
                    }
                }
            }
            out.writeBytes("\r\n--" + limite + "--\r\n");
        }

        int codigo = con.getResponseCode();
        try (InputStream in = codigo < 400 ? con.getInputStream() : con.getErrorStream()) {
            if (in == null) return "{}";
            // Nada de `readAllBytes`: es API 33 y el mínimo aquí es 29.
            java.io.ByteArrayOutputStream cuerpo = new java.io.ByteArrayOutputStream();
            byte[] trozo = new byte[8192];
            int leidos;
            while ((leidos = in.read(trozo)) != -1) cuerpo.write(trozo, 0, leidos);
            return cuerpo.toString("UTF-8");
        } finally {
            con.disconnect();
        }
    }

    private void campo(DataOutputStream out, String limite, String nombre, String valor)
            throws Exception {
        out.writeBytes("--" + limite + "\r\n");
        out.writeBytes("Content-Disposition: form-data; name=\"" + nombre + "\"\r\n\r\n");
        out.write((valor == null ? "" : valor).getBytes("UTF-8"));
        out.writeBytes("\r\n");
    }

    private String nombreDe(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (i >= 0) return c.getString(i);
            }
        } catch (Exception ignorada) {
            // Da igual: con un nombre genérico se sube igual.
        }
        return "video.mp4";
    }

    // ------------------------------------------------------------------
    // Notificación, con la misma cara que la de descargas
    // ------------------------------------------------------------------
    private Notification aviso(int hechos, int total, String nombre, int pct) {
        RemoteViews vista = new RemoteViews(getPackageName(), R.layout.aviso_descargas);
        vista.setTextViewText(R.id.titulo,
            total == 1 ? "Subiendo 1 vídeo" : "Subiendo " + total + " vídeos");
        vista.setTextViewText(R.id.detalle,
            (total > 1 ? Math.min(hechos + 1, total) + " de " + total + " · " : "") + nombre);
        vista.setViewVisibility(R.id.cifras, View.GONE);
        vista.setProgressBar(R.id.barra, total == 0 ? 1 : total, hechos, false);

        Notification n = new Notification.Builder(this, CANAL)
            .setSmallIcon(R.drawable.ic_descarga)
            .setColor(0xFF15DBF9)
            .setStyle(new Notification.DecoratedCustomViewStyle())
            .setCustomContentView(vista)
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setContentIntent(volverALaApp())
            .build();
        return n;
    }

    private void notificar(Notification n) {
        getSystemService(NotificationManager.class).notify(ID_AVISO, n);
    }

    private void avisoFinal(int total) {
        RemoteViews vista = new RemoteViews(getPackageName(), R.layout.aviso_descargas);
        vista.setTextViewText(R.id.titulo,
            total == 1 ? "1 vídeo subido" : total + " vídeos subidos");
        vista.setTextViewText(R.id.detalle, "Toca para volver y repartirlos");
        vista.setViewVisibility(R.id.barra, View.GONE);
        vista.setViewVisibility(R.id.cifras, View.GONE);
        getSystemService(NotificationManager.class).notify(ID_AVISO + 1,
            new Notification.Builder(this, CANAL)
                .setSmallIcon(R.drawable.ic_descarga)
                .setColor(0xFF15DBF9)
                .setStyle(new Notification.DecoratedCustomViewStyle())
                .setCustomContentView(vista)
                .setAutoCancel(true)
                .setContentIntent(volverALaApp())
                .build());
    }

    private PendingIntent volverALaApp() {
        Intent i = new Intent(this, MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(
            this, 0, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
