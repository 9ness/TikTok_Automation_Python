package ai.nebulabs.tiktok.prueba;

/**
 * Le cuenta a la pantalla lo que va haciendo el servicio, fichero a fichero.
 *
 * Hace falta porque el servicio y la pantalla son dos cosas distintas: el
 * servicio sigue subiendo con la app cerrada, pero mientras esté abierta la
 * interfaz tiene que ir marcando cada clip como subido, no esperar al final de
 * la tanda.
 *
 * Es un callback estático y no un broadcast porque los dos viven en el MISMO
 * proceso: un `LocalBroadcastManager` metería una dependencia (y encima está
 * descatalogado) para cruzar dos objetos que se ven entre sí.
 *
 * Si la pantalla no está viva no se pierde nada: el servicio deja las
 * respuestas guardadas y se entregan al volver (`recogerResultados`).
 */
final class Avisador {

    interface Escucha {
        void subido(String nombre, String respuesta);
    }

    private static volatile Escucha escucha;

    private Avisador() {}

    static void escuchar(Escucha e) {
        escucha = e;
    }

    static void subido(Object ignorado, String nombre, String respuesta) {
        Escucha e = escucha;
        if (e == null) return;
        try {
            e.subido(nombre, respuesta);
        } catch (Throwable t) {
            // Avisar a la pantalla no puede tumbar la subida.
        }
    }
}
