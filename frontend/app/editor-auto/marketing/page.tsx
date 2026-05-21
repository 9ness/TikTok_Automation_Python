"use client";

import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  Coins,
  Crown,
  DollarSign,
  Gift,
  LineChart,
  MessageCircle,
  Repeat,
  Rocket,
  Share2,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/**
 * Esta página es un "plan de marketing analizado" para revisar con el
 * socio antes de decidir qué aplicar. NO modifica nada — solo presenta
 * propuestas estructuradas. Cuando se acuerde algo, se pasa al backend
 * (precios → /plans, descuentos → referrals service, etc.).
 *
 * Estructura:
 *  1. Resumen estratégico (1 párrafo)
 *  2. Benchmark vs competencia (tabla)
 *  3. Estrategia de pricing (corto / medio plazo)
 *  4. Plan de captación (canales + acciones)
 *  5. Referidos & retención (mecánicas)
 *  6. Upsell / cross-sell
 *  7. Riesgos & mitigaciones
 *  8. Roadmap (90 días)
 */

export default function EditorAutoMarketingPage() {
  return (
    <div className="space-y-8 p-4 sm:p-6">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <LineChart className="h-6 w-6 text-emerald-500" />
          <h1 className="text-2xl font-bold tracking-tight">
            Estrategia de marketing — Editor Auto
          </h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Propuestas analizadas para validar con el socio. <strong>No
          aplican nada</strong> hasta que se acuerden. Cuando algo se decida,
          se aplica desde la pestaña Planes o desde el código.
        </p>
      </header>

      <StrategicSummary />
      <CompetitionBenchmark />
      <PricingStrategy />
      <AcquisitionChannels />
      <ReferralsAndRetention />
      <UpsellPaths />
      <RisksAndMitigations />
      <RoadmapNext90Days />
    </div>
  );
}

// ===========================================================================
// 1. Resumen estratégico
// ===========================================================================
function StrategicSummary() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Target className="h-4 w-4 text-emerald-500" />
          Resumen estratégico
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>
          <strong>Tesis:</strong> el mercado de edición de TikTok está
          ocupado por editores freelance que cobran 600–800€/mes por entregar
          5 vídeos/día. Nuestro coste marginal es ~0.05$/vídeo, lo que nos
          permite ofrecer el <strong>mismo output a 40–60% de su precio</strong>
          con margen bruto &gt;95%. La ventaja desaparece si los clientes
          perciben que es IA — por eso el procesamiento se hace dentro de
          una ventana horaria, con espaciado entre vídeos.
        </p>
        <p>
          <strong>Plan de 90 días:</strong> captar los primeros 20 clientes
          a 249€/mes (plan Pro, precio &quot;early-bird&quot;) → validar
          retención mes 2 → subir precio a 349€/mes para nuevos clientes
          mientras los primeros 20 mantienen el precio old → escalar canales
          de adquisición.
        </p>
        <div className="grid gap-2 sm:grid-cols-3">
          <Kpi
            label="Objetivo 90d"
            value="20 clientes"
            sub="Pro a 249€/mes"
            icon={<Users className="h-4 w-4" />}
          />
          <Kpi
            label="MRR objetivo"
            value="~5.000€"
            sub="margen ~4.500€"
            icon={<TrendingUp className="h-4 w-4" />}
          />
          <Kpi
            label="Punto de equilibrio"
            value="1 cliente"
            sub="cubre costes API"
            icon={<Coins className="h-4 w-4" />}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function Kpi({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-md border bg-card/40 p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-xl font-bold">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

// ===========================================================================
// 2. Benchmark competencia
// ===========================================================================
function CompetitionBenchmark() {
  const rows = [
    {
      name: "Editor freelance (Upwork medio)",
      price: "600–800€/mes",
      output: "5 vídeos/día",
      eurPerVid: "4–5,3€",
      pros: "Trato humano",
      cons: "Lento, bloqueos por enfermedad, suben precio con el tiempo",
    },
    {
      name: "Agencia local Madrid/BCN",
      price: "1.200–2.500€/mes",
      output: "5–10 vídeos/día",
      eurPerVid: "5–8€",
      pros: "Equipo, soporte premium",
      cons: "Caro, contratos largos, onboarding lento",
    },
    {
      name: "CapCut Pro + freelance",
      price: "≈400€/mes",
      output: "Variable",
      eurPerVid: "n/a",
      pros: "Más control creativo",
      cons: "El cliente edita él mismo o paga doble",
    },
    {
      name: "✅ Nosotros — Pro",
      price: "249€ (early-bird) / 349€ regular",
      output: "5 vídeos/día",
      eurPerVid: "1,7€ / 2,3€",
      pros: "Mismo output, 40–60% más barato, entrega 24h",
      cons: "Cliente sin contacto humano directo (mitigable con Telegram VIP)",
      highlight: true,
    },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Crown className="h-4 w-4 text-amber-500" />
          Benchmark vs competencia
        </CardTitle>
        <CardDescription>
          Para 5 vídeos/día consistentes con subtítulos + corte de silencios.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs sm:text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3">Opción</th>
              <th className="py-2 pr-3">Precio</th>
              <th className="py-2 pr-3">Output</th>
              <th className="py-2 pr-3">€/vídeo</th>
              <th className="py-2 pr-3">Pros</th>
              <th className="py-2">Contras</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.name}
                className={`border-b last:border-0 ${
                  r.highlight ? "bg-emerald-500/5 font-medium" : ""
                }`}
              >
                <td className="py-2 pr-3">{r.name}</td>
                <td className="py-2 pr-3 whitespace-nowrap">{r.price}</td>
                <td className="py-2 pr-3 whitespace-nowrap">{r.output}</td>
                <td className="py-2 pr-3 font-mono">{r.eurPerVid}</td>
                <td className="py-2 pr-3 text-muted-foreground">{r.pros}</td>
                <td className="py-2 text-muted-foreground">{r.cons}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

// ===========================================================================
// 3. Estrategia de pricing
// ===========================================================================
function PricingStrategy() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <DollarSign className="h-4 w-4 text-emerald-500" />
          Estrategia de pricing — corto y medio plazo
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        <Proposal
          tag="Corto plazo (mes 1-2)"
          title="Tarifa early-bird Pro 249€"
          body="Los primeros 20 clientes entran a 249€/mes (vs 349€ regular). Comunicar como precio fundador, locked-in mientras mantengan el plan. Crea urgencia (slots limitados visibles en la landing). Acuerdo con socio para parar promos individuales — todo el descuento se canaliza por referidos."
        />
        <Proposal
          tag="Corto plazo"
          title="Trial gratuito 5 vídeos / 7 días"
          body="Sin tarjeta. El cliente sube hasta 5 vídeos en 7 días, ve el resultado, decide. Cap 50 trials totales para evitar abuso. Solo Starter+Pro pueden upgradear desde Trial. KPI: tasa conversión trial→pago objetivo &gt;30%."
        />
        <Proposal
          tag="Medio plazo (mes 3-4)"
          title="Salto Pro: 249 → 349"
          body="Cuando lleguemos a 15-20 clientes, subimos precio a nuevos. Old clients siguen en 249 (lock-in). Mensaje al cliente nuevo: 'oferta de fundadores agotada, gracias por venir'."
        />
        <Proposal
          tag="Medio plazo"
          title="Plan anual con 15% descuento"
          body="Pro 349€/mes vs 297€/mes (3.564€/año). Atrapa al cliente 12 meses, reduce churn, cash up-front (3.564€ × N clientes = colchón para escalar)."
        />
        <Proposal
          tag="Corto plazo"
          title="Add-ons opt-in por tool premium"
          body="silence_cutter usa GPT-4o (~0.02$/vídeo). Si en el futuro añadimos voiceover IA o avatares, va como add-on: +50€/mes activa 'paquete IA avanzada' (más herramientas)."
        />
        <Proposal
          tag="Medio plazo"
          title="Plan agencia white-label"
          body="999€+/mes con flujo personalizado, soporte directo, sin marca visible. Ya está creado en el seeder — captar 1-2 agencias para validar precio y modelo."
        />
      </CardContent>
    </Card>
  );
}

function Proposal({
  tag,
  title,
  body,
}: {
  tag: string;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-md border bg-card/40 p-3">
      <Badge variant="outline" className="mb-2 text-[10px] uppercase tracking-wider">
        {tag}
      </Badge>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        {body}
      </p>
    </div>
  );
}

// ===========================================================================
// 4. Plan de captación (canales + acciones)
// ===========================================================================
function AcquisitionChannels() {
  const channels = [
    {
      icon: <Rocket className="h-4 w-4 text-rose-500" />,
      title: "TikTok orgánico (cuenta propia)",
      hook: "Vídeos editados por NUESTRA herramienta enseñando antes/después",
      ack: "Coste 0€, latencia 4-6 sem para tracción",
      action: "10 vídeos/semana, hooks 'cómo edito 5 vídeos en 30s'",
    },
    {
      icon: <MessageCircle className="h-4 w-4 text-blue-500" />,
      title: "DMs a creadores 5k–50k followers",
      hook: "Mensaje personalizado ofreciendo trial gratis (sin spam)",
      ack: "Tasa respuesta ~10-15%, conversión a trial ~30%",
      action: "30 DMs/día, foco nichos: cocina, gaming, finanzas, GYM",
    },
    {
      icon: <Share2 className="h-4 w-4 text-amber-500" />,
      title: "Reddit / Twitter / Discord servers",
      hook: "Posts en r/Tiktokhelp, comunidades de creators",
      ack: "Bajo CTR pero alta intención",
      action: "1 post/semana en 3 comunidades. NUNCA spam, formato 'soft-sell'",
    },
    {
      icon: <Crown className="h-4 w-4 text-violet-500" />,
      title: "Influencer afiliado (1 grande)",
      hook: "Coger un creator con 50k-200k follow, regalarle 3 meses Pro, pedirle review",
      ack: "Coste: 3 × 249 = 747€ en revenue cesado",
      action: "Solo 1, elegido con cuidado. Después suyo, opera con código de referido + 30% comisión recurrente vitalicia",
    },
    {
      icon: <Calendar className="h-4 w-4 text-teal-500" />,
      title: "Webinar / Demo en directo (mensual)",
      hook: "30min: caso real de cliente, antes/después, Q&A",
      ack: "Build trust, justifica precio",
      action: "1ª demo en mes 2, registrar y reutilizar el vídeo",
    },
    {
      icon: <ShieldCheck className="h-4 w-4 text-emerald-500" />,
      title: "Casos de uso + testimonios públicos",
      hook: "Pedir 3 clientes happy → testimonial vídeo de 30s",
      ack: "Conversión landing +20-40% con testimoniales",
      action: "Tras mes 1, comprobar feedback y pedir el favor",
    },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Zap className="h-4 w-4 text-amber-500" />
          Plan de captación — 6 canales priorizados
        </CardTitle>
        <CardDescription>
          Empezar por los 2 primeros (coste ~0€). Activar el resto cuando
          haya capacidad de hablar con leads.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {channels.map((c, i) => (
          <div
            key={c.title}
            className="flex items-start gap-3 rounded-md border bg-card/40 p-3"
          >
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">
              {i + 1}
            </div>
            <div className="flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                {c.icon}
                <h3 className="text-sm font-semibold">{c.title}</h3>
              </div>
              <p className="text-xs text-muted-foreground">
                <strong>Hook:</strong> {c.hook}
              </p>
              <p className="text-xs text-muted-foreground">
                <strong>Esperado:</strong> {c.ack}
              </p>
              <p className="text-xs">
                <ArrowRight className="mr-1 inline h-3 w-3" />
                {c.action}
              </p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ===========================================================================
// 5. Referidos & retención
// ===========================================================================
function ReferralsAndRetention() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Gift className="h-4 w-4 text-pink-500" />
          Referidos & retención
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2">
        <Proposal
          tag="Referidos"
          title="25% / mes por cada referido (cap 50%)"
          body="Cada user tiene un código único. Si otro cliente lo usa al registrarse, el owner paga 25% menos el mes siguiente. Acumulable hasta 50% (2+ referidos en el mismo mes). Implementado ya en backend → falta cobrar/aplicar el descuento al facturar."
        />
        <Proposal
          tag="Referidos"
          title="Comisión vitalicia para creators"
          body="Variante para influencers que muevan volumen: 30% del MRR mientras el referido mantenga el plan. Activable como flag por user en la UI (TODO si confirmamos canal influencer)."
        />
        <Proposal
          tag="Retención"
          title="Onboarding semana 1 — check-in proactivo"
          body="Día 3: mensaje (Telegram/WhatsApp) preguntando si todo bien. Día 7: pedir feedback. Día 14: si feedback positivo, pedir testimonial. Reduce cancelaciones del mes 1 (el churn más alto)."
        />
        <Proposal
          tag="Retención"
          title="Bloqueo upgrade el día 25 del ciclo"
          body="Si el cliente Starter usa 80% de la cuota mensual antes del día 25 → email automático sugiriendo upgrade a Pro con 1 mes prorrateado. Convierte mejor cuando el dolor es reciente."
        />
        <Proposal
          tag="Retención"
          title="'Vacaciones' opcionales"
          body="Permitir pausar plan 1 mes/año sin perder slot promo. Reduce cancelaciones por 'estoy de viaje'. Implementable como Subscription.status='paused' (ya soportado en backend)."
        />
        <Proposal
          tag="Retención"
          title="Comunicar tiempos reales de entrega"
          body="No prometer 'instantáneo'. Comunicar 'entrega en horario laboral 9-19h CET, normalmente en 1-3h'. Marketing crea expectativa correcta → menos quejas, refuerza imagen humana."
        />
      </CardContent>
    </Card>
  );
}

// ===========================================================================
// 6. Upsell / cross-sell
// ===========================================================================
function UpsellPaths() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <TrendingUp className="h-4 w-4 text-emerald-500" />
          Upsell &amp; expansión
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <UpsellRow
          from="Trial"
          to="Starter (149€)"
          trigger="Trial agota sus 5 vídeos en &lt;7 días"
          tactic="Email/DM con código -20% primer mes"
        />
        <UpsellRow
          from="Starter (149€)"
          to="Pro (249€)"
          trigger="80% cuota diaria consumida 3+ días seguidos"
          tactic="Banner in-app + email '¿necesitas más vídeos?'"
        />
        <UpsellRow
          from="Pro (249€)"
          to="Studio (549€)"
          trigger="Cliente añade 2da cuenta o pide flujo distinto"
          tactic="Llamada de 15min, ofrecer flow personalizado"
        />
        <UpsellRow
          from="Studio"
          to="Agencia (999€+)"
          trigger="Cliente gestiona 3+ marcas distintas"
          tactic="Propuesta white-label + acuerdo anual"
        />
      </CardContent>
    </Card>
  );
}

function UpsellRow({
  from,
  to,
  trigger,
  tactic,
}: {
  from: string;
  to: string;
  trigger: string;
  tactic: string;
}) {
  return (
    <div className="grid gap-2 rounded-md border bg-card/40 p-3 sm:grid-cols-[1fr_auto_1fr]">
      <div className="text-xs">
        <span className="text-muted-foreground">De </span>
        <strong>{from}</strong>
        <div className="mt-1 text-muted-foreground">
          Trigger: <span dangerouslySetInnerHTML={{ __html: trigger }} />
        </div>
      </div>
      <ArrowRight className="hidden h-4 w-4 self-center text-muted-foreground sm:block" />
      <div className="text-xs">
        <span className="text-muted-foreground">A </span>
        <strong className="text-emerald-600 dark:text-emerald-400">{to}</strong>
        <div className="mt-1 text-muted-foreground">Tactic: {tactic}</div>
      </div>
    </div>
  );
}

// ===========================================================================
// 7. Riesgos & mitigaciones
// ===========================================================================
function RisksAndMitigations() {
  const risks = [
    {
      title: "Cliente detecta que es IA",
      desc: "Si el cliente percibe que el output es generado por IA, perdemos la premium percibida vs editor humano.",
      mitigation:
        "Procesar dentro de ventana 9-19h con espaciado 20-30min. Comunicar tiempos humanos. NO mencionar 'AI' en marketing inicial — pivotar luego cuando la marca esté hecha.",
    },
    {
      title: "Servidor cae / GPU sobrecargada",
      desc: "PC privado, 24/7. Un usuario con cola enorme puede colapsar el resto.",
      mitigation:
        "Cuota diaria por user. Spacing entre vídeos. Plan B: alquilar GPU cloud (RunPod/Vast) si MRR &gt; 2k€.",
    },
    {
      title: "Copyright / banneo TikTok",
      desc: "Si el cliente mete contenido con copyright, el output también lo tiene. Cliente culpa al servicio.",
      mitigation:
        "TOS explícitos: 'el contenido subido es responsabilidad del cliente'. Anti-copy ya implementado en otros nichos — replicar para Editor Auto.",
    },
    {
      title: "Drive como cuello de botella",
      desc: "Drive personal con cuota gratuita ~15GB. Con 20 clientes × 150 vídeos × 50MB = ~150GB.",
      mitigation:
        "Migrar a Drive de pago (Workspace 2TB ~9€/mes) o S3 cuando lleguemos a 5+ clientes activos.",
    },
    {
      title: "Cancelación masiva por novedad",
      desc: "Mes 2-3 algunos clientes prueban y se van. Churn alto antes de estabilizar.",
      mitigation:
        "Anual con 15% descuento. Onboarding proactivo semana 1. Casos de éxito visibles en landing.",
    },
    {
      title: "Coste API sube (OpenAI/MiniMax)",
      desc: "gpt-4o sube precio o cambia condiciones. Hoy ~0.02$/vídeo en silence_cutter.",
      mitigation:
        "Tarifas blindadas locked-in solo 12 meses. Cláusula 'sujeto a cambios con 30 días de aviso'. Tener un plan B en local (whisper grande) para silence_cutter sin GPT.",
    },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4 text-rose-500" />
          Riesgos & mitigaciones
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {risks.map((r) => (
          <div
            key={r.title}
            className="rounded-md border border-rose-500/20 bg-rose-500/5 p-3"
          >
            <h3 className="text-sm font-semibold text-rose-700 dark:text-rose-300">
              ⚠️ {r.title}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">{r.desc}</p>
            <p className="mt-1.5 flex gap-1.5 text-xs">
              <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
              <span>
                <strong>Mitigación:</strong> {r.mitigation}
              </span>
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ===========================================================================
// 8. Roadmap 90 días
// ===========================================================================
function RoadmapNext90Days() {
  const phases = [
    {
      label: "Mes 1 — Validación",
      goal: "5 clientes Pro a 249€ (= 1.245€ MRR)",
      actions: [
        "Lanzar Pro a 249€ con landing simple",
        "Conseguir primeros 5 clientes via DMs a creators conocidos",
        "Configurar pago manual PayPal/Bizum + asignación de plan manual",
        "Tracker en Sheets: signup → activación → primer vídeo",
      ],
    },
    {
      label: "Mes 2 — Refinar",
      goal: "10-12 clientes (= ~3.000€ MRR)",
      actions: [
        "Activar canal TikTok orgánico (10 vídeos/sem)",
        "Pedir testimoniales a los 5 primeros clientes happy",
        "Lanzar referidos visibles desde la UI del cliente (futura web pública)",
        "Implementar trial 7 días",
      ],
    },
    {
      label: "Mes 3 — Escalar",
      goal: "20 clientes Pro + 1-2 Studio (= ~5.500€ MRR)",
      actions: [
        "Cerrar promo early-bird 249€, lanzar precio regular 349€",
        "Aprobar/rechazar canal influencer afiliado tras coste/beneficio",
        "Webinar mensual público",
        "Decidir si abrimos signup público o seguimos onboarding manual",
      ],
    },
  ];
  return (
    <Card className="border-emerald-500/40 bg-emerald-50/30 dark:bg-emerald-950/10">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Repeat className="h-4 w-4 text-emerald-500" />
          Roadmap 90 días
        </CardTitle>
        <CardDescription>
          KPI principal: MRR mes 3 &gt; 5.000€ y churn &lt; 15%.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 lg:grid-cols-3">
        {phases.map((p) => (
          <div
            key={p.label}
            className="rounded-md border bg-background p-3 shadow-sm"
          >
            <h3 className="text-sm font-bold">{p.label}</h3>
            <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">
              🎯 {p.goal}
            </p>
            <ul className="mt-2 space-y-1">
              {p.actions.map((a) => (
                <li
                  key={a}
                  className="flex items-start gap-1.5 text-xs text-muted-foreground"
                >
                  <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
