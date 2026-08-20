package ai.nebulabs.tiktok.prueba;

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
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.OutputStream;
import java.net.URLDecoder;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * APK de PRUEBA. Responde una sola pregunta: ¿puede un WebView guardar las
 * descargas en una carpeta propia, `Download/TTShopAIPro/`?
 *
 * La app de verdad es una TWA (Chrome sin barra) y ahí las descargas las
 * gestiona Chrome: no hay dónde engancharse. Esto prueba la alternativa antes
 * de tocar nada, que es lo que pidió el operador.
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

    private static final String TAG = "PruebaDescargas";
    /** La carpeta que se quiere conseguir, dentro de Descargas. */
    private static final String CARPETA = "TTShopAIPro";
    /** El mismo dominio que la app buena (`android/twa-manifest.json`). */
    private static final String URL_APP = "https://tiktok-factory.tailbff00e.ts.net/";

    private WebView web;
    private AvisoDescargas avisosDescarga;
    /** Dónde devolver los ficheros que elija el usuario (ver `onShowFileChooser`). */
    private ValueCallback<Uri[]> esperandoFicheros;
    private static final int PEDIR_FICHEROS = 1;

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        // Se identifica para que la web sepa que está dentro de ESTA app. Sin
        // esto salía el banner de "instala la app", que ofrece la APK BUENA, y
        // es facilísimo pulsarlo por error estando en la de prueba.
        s.setUserAgentString(s.getUserAgentString() + " TTShopPrueba/1");
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
             * Se apunta como hallazgo de la prueba: una migración a WebView no
             * es solo rehacer las descargas, también las SUBIDAS.
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
            @Override
            public void onPageFinished(WebView v, String url) {
                // El nombre del fichero vive en el atributo `download` del
                // enlace, y al llegar como `blob:` ya se ha perdido. Se apunta
                // en cuanto se pulsa, ANTES de que el navegador haga nada.
                v.evaluateJavascript(
                    "(function(){if(window.__pruebaEnganchada)return;" +
                    "window.__pruebaEnganchada=1;window.__ultimoNombre='';" +
                    "document.addEventListener('click',function(e){" +
                    "var a=e.target&&e.target.closest?e.target.closest('a[download]'):null;" +
                    "if(a){window.__ultimoNombre=a.getAttribute('download')||'';}}," +
                    "true);})()", null);
            }
        });
        web.addJavascriptInterface(new Puente(), "PruebaAndroid");

        web.setDownloadListener((url, agente, disposicion, tipo, tamano) -> {
            if (url.startsWith("blob:")) {
                pedirBlobAlNavegador(url);
                return;
            }
            bajarConDownloadManager(url, disposicion, tipo);
        });

        avisosDescarga = new AvisoDescargas(this);
        pedirPermisoDeNotificaciones();
        // De cuándo es esta APK. Con varias reinstalaciones seguidas es lo
        // único que dice si se está probando la última o una vieja.
        aviso("Prueba del " + getString(R.string.build_date));
        web.loadUrl(URL_APP);
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
     * lo lea y lo mande en base64. Es el punto flojo y por eso se prueba.
     */
    private void pedirBlobAlNavegador(String url) {
        String js =
            "(function(){var x=new XMLHttpRequest();x.open('GET','" + url + "',true);" +
            "x.responseType='blob';x.onload=function(){" +
            "var r=new FileReader();r.onloadend=function(){" +
            "PruebaAndroid.guardarBlob(r.result, window.__ultimoNombre||'descarga', x.response.type);};" +
            "r.onerror=function(){PruebaAndroid.fallo('no se pudo leer el blob');};" +
            "r.readAsDataURL(x.response);};" +
            "x.onerror=function(){PruebaAndroid.fallo('no se pudo pedir el blob');};" +
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
        // Hay que contestar SIEMPRE, aunque se cancele: si no, el input se
        // queda bloqueado y no vuelve a abrirse nunca.
        esperandoFicheros.onReceiveValue(
            WebChromeClient.FileChooserParams.parseResult(resultado, datos));
        esperandoFicheros = null;
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
