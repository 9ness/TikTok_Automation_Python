package com.nebulabsai.tiktokauto;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.WebResourceRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import java.io.OutputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.net.URLDecoder;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * La app: un WebView que carga la web.
 *
 * Antes era una TWA (Chrome sin barra) y las descargas las gestionaba Chrome:
 * no había dónde engancharse para elegir carpeta ni para seguir subiendo con el
 * móvil bloqueado. El porqué del cambio está en `APK.md`.
 *
 * Los dos casos que tiene la app, y por qué no son el mismo problema:
 *
 *  1. UNA a una — `<a href="https://…" download>`. El `DownloadListener` recibe
 *     la URL y `DownloadManager` la baja donde se le diga. Hay que pasarle la
 *     COOKIE a mano: el fichero está detrás de sesión y sin ella baja un HTML
 *     de login con extensión .mp4.
 *
 *  2. EN TANDA — la app baja el contenido a un `blob:` para que los ficheros se
 *     creen en orden. Con `blob:` el `DownloadListener` NI SE DISPARA: el dato
 *     ya está en el navegador y no hay URL que darle a nadie. Hay que pasar los
 *     bytes al lado Java, y ahí es donde esto puede romperse con vídeos de
 *     20 MB (el base64 los hincha un tercio y se queda todo en memoria).
 */
public class MainActivity extends Activity {

    private static final String TAG = "TikTokAuto";
    /** La carpeta que se quiere conseguir, dentro de Descargas. */
    private static final String CARPETA = "TTShopAIPro";
    /** El mismo dominio que la app buena (`android/twa-manifest.json`). */
    private static final String URL_APP = "https://tiktok-factory.tailbff00e.ts.net/";

    private WebView web;
    private SwipeRefreshLayout deslizar;
    private AvisoDescargas avisosDescarga;
    /** Lo ÚLTIMO que eligió el usuario en el selector: nombre → `content://`.
     *
     *  La web tiene los `File` del `<input type="file">` y aquí se tienen las
     *  URIs del mismo selector. Se casan por NOMBRE, que es lo único que
     *  comparten los dos lados, y así el servicio puede leer los bytes sin que
     *  la web se los pase (pasarlos costaría base64 de 30 MB por vídeo). */
    private final Map<String, Uri> ultimaSeleccion = new LinkedHashMap<>();
    /** Dónde devolver los ficheros que elija el usuario (ver `onShowFileChooser`). */
    private ValueCallback<Uri[]> esperandoFicheros;
    private static final int PEDIR_FICHEROS = 1;

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        web = new WebView(this);
        // Deslizar hacia abajo para recargar. Un WebView no lo trae: en la app
        // de siempre lo pone Chrome, aquí hay que montarlo.
        deslizar = new SwipeRefreshLayout(this);
        deslizar.addView(web);
        deslizar.setColorSchemeColors(0xFF15DBF9, 0xFFA855F7);
        deslizar.setProgressBackgroundColorSchemeColor(0xFF0A0A0B);
        deslizar.setOnRefreshListener(() -> web.reload());
        // Solo se dispara ARRIBA DEL TODO: si no, al desplazarse por una lista
        // larga el gesto se lo comía el recargador y la página no bajaba.
        deslizar.setOnChildScrollUpCallback((padre, hijo) -> web.getScrollY() > 0);
        setContentView(deslizar);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        // Se identifica para que la web sepa que está dentro de la app. Sin
        // esto sale el banner de "instala la app" dentro de la propia app: un
        // WebView no cumple `display-mode: standalone` ni tiene el referrer
        // `android-app://` que delataba a la TWA.
        s.setUserAgentString(s.getUserAgentString() + " TTShopApp/1");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);

        web.setWebChromeClient(new WebChromeClient() {
            /**
             * SIN ESTO, tocar "Clip 1" no hace absolutamente nada.
             *
             * Es otra cosa que un WebView no trae de serie: el
             * `<input type="file">` no abre ningún selector si la app no lo
             * implementa. En la TWA funciona solo porque es Chrome.
             *
             * Se descubrió al migrar: pasar a WebView no es solo rehacer las
             * descargas, también las SUBIDAS.
             */
            @Override
            public boolean onShowFileChooser(WebView v,
                                             ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (esperandoFicheros != null) esperandoFicheros.onReceiveValue(null);
                esperandoFicheros = callback;
                try {
                    startActivityForResult(params.createIntent(), PEDIR_FICHEROS);
                    return true;
                } catch (Exception e) {
                    esperandoFicheros = null;
                    aviso("No se pudo abrir el selector de ficheros: " + e);
                    return false;
                }
            }
        });
        web.setWebViewClient(new WebViewClient() {
            /**
             * Todo lo que no sea NUESTRA web se le pasa a Android.
             *
             * Un WebView solo entiende `http`/`https`. La ficha de un producto
             * en TikTok Shop acaba redirigiendo a `intent://ec/pdp?…`, que es
             * cómo TikTok pide que se abra su app, y eso aquí moría con
             * `ERR_UNKNOWN_URL_SCHEME` en una pantalla blanca. En Chrome —y por
             * tanto en la TWA— funcionaba porque Chrome sí sabe resolver esos
             * enlaces.
             *
             * Se hace por descarte y no listando esquemas: `intent://`,
             * `tiktok://`, `market://`, `tel:`, `mailto:`… son todos el mismo
             * caso. Y los `https` de FUERA también se mandan al sistema: son
             * fichas de producto que se abren para copiar algo, y dejarlas
             * dentro de esta app deja al operador atrapado en una web ajena.
             */
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                Uri destino = req.getUrl();
                String host = destino.getHost();
                if (host != null && host.equalsIgnoreCase(Uri.parse(URL_APP).getHost())) {
                    return false;   // lo nuestro se queda dentro
                }
                return abrirFuera(destino.toString());
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                if (deslizar != null) deslizar.setRefreshing(false);
                // El nombre del fichero vive en el atributo `download` del
                // enlace, y al llegar como `blob:` ya se ha perdido. Se apunta
                // en cuanto se pulsa, ANTES de que el navegador haga nada.
                v.evaluateJavascript(
                    "(function(){if(window.__appEnganchada)return;" +
                    "window.__appEnganchada=1;window.__ultimoNombre='';" +
                    "document.addEventListener('click',function(e){" +
                    "var a=e.target&&e.target.closest?e.target.closest('a[download]'):null;" +
                    "if(a){window.__ultimoNombre=a.getAttribute('download')||'';}}," +
                    "true);})()", null);
            }
        });
        web.addJavascriptInterface(new Puente(), "AppAndroid");

        web.setDownloadListener((url, agente, disposicion, tipo, tamano) -> {
            if (url.startsWith("blob:")) {
                pedirBlobAlNavegador(url);
                return;
            }
            bajarConDownloadManager(url, disposicion, tipo);
        });

        avisosDescarga = new AvisoDescargas(this);
        // Cada fichero que sube el servicio se le cuenta a la pantalla en el
        // momento, para que marque ese hueco sin esperar al final de la tanda.
        Avisador.escuchar((nombre, respuesta) -> runOnUiThread(() -> {
            if (web == null) return;
            String js = "if(window.__subidaAppFichero)window.__subidaAppFichero("
                + org.json.JSONObject.quote(nombre) + ","
                + org.json.JSONObject.quote(respuesta) + ")";
            web.evaluateJavascript(js, null);
        }));
        pedirPermisoDeNotificaciones();
        pedirSalirDelAhorroDeBateria();
        // Antes esto no hacía falta: la app era una carcasa de la web y se
        // actualizaba sola con cada despliegue. Ahora trae cosas propias
        // (descargas, subida en segundo plano) que solo llegan con una APK
        // nueva, así que hay que avisar de que existe.
        Actualizaciones.comprobar(this);
        web.loadUrl(URL_APP);
    }

    /** Los dos paquetes con los que se publica TikTok. El segundo es el que
     *  llevan algunos móviles según de dónde vengan; probar solo el primero
     *  dejaba a esos abriendo el navegador. */
    private static final String[] PAQUETES_TIKTOK = {
        "com.zhiliaoapp.musically",
        "com.ss.android.ugc.trill",
    };

    /**
     * Abre un enlace fuera de esta app, y en la APP de TikTok si se puede.
     *
     * Que abra la app y no el navegador no es un detalle: la ficha se abre para
     * meter el producto en el escaparate, y eso solo se puede hacer estando
     * dentro de TikTok con la cuenta puesta. En el navegador se acaba en una
     * página que pide instalar la app.
     *
     * Se intenta en este orden, y cada paso solo se usa si el anterior no ha
     * podido:
     *   1. El enlace, pero dirigido a TikTok por su nombre de paquete.
     *   2. Cualquier app que NO sea un navegador (`REQUIRE_NON_BROWSER`).
     *   3. Lo que sea — navegador incluido —, que es mejor que no abrir nada.
     *
     * Los `intent://` ya vienen apuntando a su app, así que van por su lado; lo
     * que traen dentro es un `browser_fallback_url` para cuando esa app no está
     * instalada, y sin usarlo el operador se queda en blanco sin saber por qué.
     */
    private boolean abrirFuera(String url) {
        if (url.startsWith("intent:")) {
            try {
                Intent intent = Intent.parseUri(url, Intent.URI_INTENT_SCHEME);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try {
                    startActivity(intent);
                    return true;
                } catch (android.content.ActivityNotFoundException sinApp) {
                    String plan_b = intent.getStringExtra("browser_fallback_url");
                    if (plan_b != null) return abrirFuera(plan_b);
                    aviso("No tienes instalada la app que abre ese enlace");
                    return true;
                }
            } catch (Exception e) {
                aviso("Enlace que no se entiende: " + e);
                return true;
            }
        }

        Uri destino = Uri.parse(url);

        for (String paquete : PAQUETES_TIKTOK) {
            Intent enLaApp = new Intent(Intent.ACTION_VIEW, destino);
            enLaApp.setPackage(paquete);
            enLaApp.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                startActivity(enLaApp);
                return true;
            } catch (android.content.ActivityNotFoundException noEstaONoLoAbre) {
                // Ni instalada, ni sabe abrir ese enlace: se prueba el siguiente.
            }
        }

        // Android 11+ sabe decir "cualquiera menos un navegador", que es lo que
        // hace falta cuando el enlace lo puede atender otra app instalada.
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
            Intent noNavegador = new Intent(Intent.ACTION_VIEW, destino);
            noNavegador.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_REQUIRE_NON_BROWSER);
            try {
                startActivity(noNavegador);
                return true;
            } catch (android.content.ActivityNotFoundException soloNavegadores) {
                // Solo hay navegadores: se abre uno, abajo.
            }
        }

        try {
            Intent ver = new Intent(Intent.ACTION_VIEW, destino);
            ver.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(ver);
            return true;
        } catch (Exception e) {
            aviso("No se pudo abrir el enlace: " + e);
            return true;
        }
    }

    /**
     * En Android 13+ hay que PEDIR poder notificar. Sin esto el gestor de
     * descargas baja igual pero en silencio: no se ve la barra de progreso ni
     * el "listo", que es justo lo que se echaba de menos frente a Chrome.
     */
    private void pedirPermisoDeNotificaciones() {
        if (android.os.Build.VERSION.SDK_INT < 33) return;
        if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
            return;
        }
        requestPermissions(
            new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 2);
    }

    /**
     * Pide quedar FUERA del ahorro de batería.
     *
     * Es lo que más corta las tandas largas: con el ahorro puesto, Android
     * duerme la app en cuanto se apaga la pantalla y la subida se queda a
     * medias. Se pregunta UNA vez; si se dice que no, todo sigue funcionando,
     * solo que con menos margen.
     */
    private void pedirSalirDelAhorroDeBateria() {
        try {
            android.os.PowerManager pm = getSystemService(android.os.PowerManager.class);
            if (pm.isIgnoringBatteryOptimizations(getPackageName())) return;
            startActivity(new Intent(
                android.provider.Settings
                    .ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:" + getPackageName())));
        } catch (Exception ignorada) {
            // Hay móviles que no traen esa pantalla; no es imprescindible.
        }
    }

    /** Se queda con lo elegido para que el servicio pueda subirlo luego. */
    private void recordarSeleccion(Intent datos) {
        if (datos == null) return;
        ultimaSeleccion.clear();
        java.util.List<Uri> uris = new ArrayList<>();
        if (datos.getClipData() != null) {
            for (int i = 0; i < datos.getClipData().getItemCount(); i++) {
                uris.add(datos.getClipData().getItemAt(i).getUri());
            }
        } else if (datos.getData() != null) {
            uris.add(datos.getData());
        }
        for (Uri u : uris) {
            try {
                // Sin esto el permiso de lectura se pierde en cuanto el
                // servicio intenta abrir el fichero desde otro proceso.
                getContentResolver().takePersistableUriPermission(
                    u, Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } catch (Exception ignorada) {
                // No todos los selectores lo permiten; con el permiso temporal
                // de la propia Intent suele bastar.
            }
            ultimaSeleccion.put(nombreDeUri(u), u);
        }
    }

    private String nombreDeUri(Uri uri) {
        try (android.database.Cursor c =
                 getContentResolver().query(uri, null, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int i = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME);
                if (i >= 0) return c.getString(i);
            }
        } catch (Exception ignorada) {
            // Da igual: se usará el último trozo de la URI.
        }
        String s = uri.getLastPathSegment();
        return s == null ? uri.toString() : s;
    }

    /** El nombre de fichero que manda el servidor, con los acentos bien.
     *
     *  Una cabecera HTTP no puede llevar caracteres fuera de ASCII, así que un
     *  nombre con tildes viaja como `filename*=utf-8''Ergon%C3%B3mica.mp4`
     *  (RFC 5987). `URLUtil.guessFileName` no entiende esa forma y devolvía
     *  "Ergon?mica". Se lee a mano y, si no está, se cae en lo de siempre.
     */
    private String nombreDelServidor(String url, String disposicion, String tipo) {
        if (disposicion != null) {
            Matcher m = Pattern.compile(
                "filename\\*\\s*=\\s*utf-8''([^;]+)", Pattern.CASE_INSENSITIVE
            ).matcher(disposicion);
            if (m.find()) {
                try {
                    return URLDecoder.decode(m.group(1).trim(), "UTF-8");
                } catch (Exception ignorada) {
                    // Si viniera mal codificado, mejor el nombre de siempre.
                }
            }
        }
        return URLUtil.guessFileName(url, disposicion, tipo);
    }

    /** Caso 1: URL normal. Lo hace `DownloadManager`, que sabe poner subcarpeta. */
    private void bajarConDownloadManager(String url, String disposicion, String tipo) {
        try {
            String nombre = nombreDelServidor(url, disposicion, tipo);
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            r.setMimeType(tipo);
            // Sin la cookie de sesión el servidor devuelve el login.
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) r.addRequestHeader("Cookie", cookie);
            // Su notificación se apaga: pone UNA por fichero y con diez
            // vídeos eran diez avisos iguales. La nuestra las resume en una
            // sola con el progreso de toda la tanda (ver `AvisoDescargas`).
            r.setNotificationVisibility(
                DownloadManager.Request.VISIBILITY_HIDDEN);
            // ESTO es lo que se está probando.
            r.setDestinationInExternalPublicDir(
                Environment.DIRECTORY_DOWNLOADS, CARPETA + "/" + nombre);
            long id = ((DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE))
                .enqueue(r);
            avisosDescarga.empezada(id, nombre);
        } catch (Exception e) {
            Log.e(TAG, "fallo con DownloadManager", e);
            aviso("Falló la descarga normal: " + e);
        }
    }

    /**
     * Caso 2: `blob:`. El dato ya está en el navegador, así que se le pide que
     * lo lea y lo mande en base64. Es el punto flojo: lo usan los carruseles y
     * no se ha probado con tandas grandes.
     */
    private void pedirBlobAlNavegador(String url) {
        String js =
            "(function(){var x=new XMLHttpRequest();x.open('GET','" + url + "',true);" +
            "x.responseType='blob';x.onload=function(){" +
            "var r=new FileReader();r.onloadend=function(){" +
            "AppAndroid.guardarBlob(r.result, window.__ultimoNombre||'descarga', x.response.type);};" +
            "r.onerror=function(){AppAndroid.fallo('no se pudo leer el blob');};" +
            "r.readAsDataURL(x.response);};" +
            "x.onerror=function(){AppAndroid.fallo('no se pudo pedir el blob');};" +
            "x.send();})()";
        web.evaluateJavascript(js, null);
    }

    /** Lo que el JavaScript puede llamar. */
    private class Puente {
        @JavascriptInterface
        public void guardarBlob(String dataUrl, String nombre, String tipo) {
            try {
                int coma = dataUrl.indexOf(',');
                byte[] datos = Base64.decode(dataUrl.substring(coma + 1), Base64.DEFAULT);
                avisosDescarga.empezadaSinGestor(nombre);
                guardarEnDescargas(nombre, tipo, datos);
                avisosDescarga.terminadaSinGestor();
            } catch (Throwable e) {
                // `Throwable` a posta: con un vídeo grande esto puede ser un
                // OutOfMemoryError, que es justo lo que se quiere descubrir.
                Log.e(TAG, "fallo guardando el blob", e);
                aviso("Falló la descarga en tanda: " + e);
            }
        }

        @JavascriptInterface
        public void fallo(String motivo) {
            aviso("Falló el blob: " + motivo);
        }

        /** ¿Puede la web delegar la subida en la app? */
        @JavascriptInterface
        public boolean puedeSubirEnSegundoPlano() {
            return true;
        }

        /**
         * La web dice QUÉ subir y A DÓNDE; los bytes los mueve el servicio.
         *
         * `tareasJson` es `[{"nombre":…,"url":…,"campos":{…}}]`. Cada tarea
         * lleva SUS campos porque los dos sitios que suben mandan cosas
         * distintas: la tanda va con `source`+`folder` y cada clip con su
         * producto, su hueco y las herramientas de esa tarjeta.
         *
         * Del fichero solo viaja el NOMBRE: se casa con la URI que se guardó
         * del selector, y así no hay que pasar 30 MB por el puente.
         */
        @JavascriptInterface
        public boolean subirVarios(String url, String apiKey, String tareasJson) {
            try {
                org.json.JSONArray entran = new org.json.JSONArray(tareasJson);
                org.json.JSONArray salen = new org.json.JSONArray();
                for (int i = 0; i < entran.length(); i++) {
                    org.json.JSONObject t = entran.getJSONObject(i);
                    String nombre = t.getString("nombre");
                    Uri u = ultimaSeleccion.get(nombre);
                    // Un fichero que no está en la última selección no se puede
                    // leer: mejor no subir esa tarea que subir otra cosa.
                    if (u == null) continue;
                    t.put("uri", u.toString());
                    if (!t.has("url")) t.put("url", url);
                    salen.put(t);
                }
                if (salen.length() == 0) return false;
                Intent i = new Intent(MainActivity.this, ServicioSubidas.class)
                    .putExtra(ServicioSubidas.EXTRA_TAREAS, salen.toString())
                    .putExtra(ServicioSubidas.EXTRA_API_KEY, apiKey)
                    .putExtra(ServicioSubidas.EXTRA_COOKIE,
                        CookieManager.getInstance().getCookie(url));
                startForegroundService(i);
                return true;
            } catch (Exception e) {
                return false;
            }
        }

        /** Lo que dejó el servicio, para que la web reparta al volver. */
        @JavascriptInterface
        public String recogerResultados() {
            android.content.SharedPreferences p = getSharedPreferences(
                ServicioSubidas.PREFS, Context.MODE_PRIVATE);
            String r = p.getString(ServicioSubidas.CLAVE_RESULTADOS, "");
            // Se entregan UNA vez: si no, al volver a abrir la app se repetiría
            // el reparto de una tanda ya repartida.
            p.edit().remove(ServicioSubidas.CLAVE_RESULTADOS).apply();
            return r;
        }
    }

    /** Escribe en `Download/TTShopAIPro/` sin pedir permisos (API 29+). */
    private void guardarEnDescargas(String nombre, String tipo, byte[] datos) throws Exception {
        ContentValues v = new ContentValues();
        v.put(MediaStore.Downloads.DISPLAY_NAME, nombre);
        if (tipo != null && !tipo.isEmpty()) v.put(MediaStore.Downloads.MIME_TYPE, tipo);
        v.put(MediaStore.Downloads.RELATIVE_PATH,
            Environment.DIRECTORY_DOWNLOADS + "/" + CARPETA);
        ContentResolver cr = getContentResolver();
        Uri destino = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
        if (destino == null) throw new IllegalStateException("MediaStore no dio destino");
        try (OutputStream out = cr.openOutputStream(destino)) {
            if (out == null) throw new IllegalStateException("no se pudo abrir el destino");
            out.write(datos);
        }
    }

    private void aviso(String texto) {
        runOnUiThread(() -> Toast.makeText(this, texto, Toast.LENGTH_LONG).show());
    }

    @Override
    protected void onActivityResult(int codigo, int resultado, Intent datos) {
        if (codigo != PEDIR_FICHEROS) {
            super.onActivityResult(codigo, resultado, datos);
            return;
        }
        if (esperandoFicheros == null) return;
        recordarSeleccion(datos);
        // Hay que contestar SIEMPRE, aunque se cancele: si no, el input se
        // queda bloqueado y no vuelve a abrirse nunca.
        esperandoFicheros.onReceiveValue(
            WebChromeClient.FileChooserParams.parseResult(resultado, datos));
        esperandoFicheros = null;
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Si el servicio terminó con la app cerrada, sus respuestas están
        // guardadas: se le entregan a la web para que reparta.
        if (web != null) {
            web.evaluateJavascript(
                "(function(){try{var r=AppAndroid.recogerResultados();"
                + "if(r&&window.__subidaAppLista)window.__subidaAppLista(r);}"
                + "catch(e){}})()", null);
        }
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
