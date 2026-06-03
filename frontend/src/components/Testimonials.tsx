import { Stethoscope, Building2, Heart, Users } from "lucide-react";

// Componentes de UI internos para evitar dependencias faltantes
const Card = ({ children, className }) => (
  <div className={`bg-white rounded-xl shadow-sm border-2 border-transparent transition-all hover:border-[#7ABBE6] hover:shadow-lg ${className}`}>
    {children}
  </div>
);

const CardContent = ({ children, className }) => (
  <div className={`p-6 ${className}`}>
    {children}
  </div>
);

const audiences = [
  {
    icon: Stethoscope,
    title: "Médicos cardiólogos",
    description: "Monitoreo continuo de pacientes con mayor precisión y acceso a datos históricos completos.",
    emoji: "👨‍⚕️",
  },
  {
    icon: Building2,
    title: "Clínicas rurales o sin especialistas",
    description: "Acceso a diagnóstico cardiológico avanzado sin necesidad de especialista on-site.",
    emoji: "🏥",
  },
  {
    icon: Heart,
    title: "Pacientes con antecedentes de arritmias",
    description: "Control permanente y alertas tempranas para prevención de eventos graves.",
    emoji: "❤️",
  },
  {
    icon: Users,
    title: "Programas de salud pública y preventiva",
    description: "Herramienta escalable para monitoreo poblacional y detección temprana.",
    emoji: "🏛️",
  },
];

export function Testimonials() {
  return (
    <section id="audience" className="py-20 bg-gradient-to-b from-[#8F9ACD]/10 to-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold mb-4" style={{ color: '#445A99' }}>
            👨‍⚕️ ¿A quién está dirigido?
          </h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Solución integral para diferentes actores del sistema de salud cardiovascular en Nicaragua.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-8">
          {audiences.map((audience, index) => {
            const IconComponent = audience.icon;
            return (
              <Card key={index}>
                <CardContent className="pt-6">
                  <div className="flex items-start gap-4 mb-4 text-left">
                    <div className="flex-shrink-0 w-12 h-12 bg-[#445A99] rounded-lg flex items-center justify-center">
                      <IconComponent className="h-6 w-6 text-white" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-2xl">{audience.emoji}</span>
                        <h3 className="text-xl font-bold" style={{ color: '#445A99' }}>{audience.title}</h3>
                      </div>
                      <p className="text-gray-600 leading-relaxed">{audience.description}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </section>
  );
}
