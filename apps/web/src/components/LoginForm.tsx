import { useState, type FormEvent } from "react";
import { useAuth } from "../context/AuthContext";
import { AlertCircle, CheckCircle2, Lock, Newspaper, User as UserIcon } from "lucide-react";

export function LoginForm() {
  const { login, register, error, clearError } = useAuth();
  const [isRegistering, setIsRegistering] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    setSuccessMessage(null);
    setIsSubmitting(true);

    try {
      if (isRegistering) {
        const msg = await register(username, password, email);
        setSuccessMessage(msg || "تم تسجيل حسابك بنجاح. حسابك بانتظار موافقة مدير النظام.");
        setIsRegistering(false);
      } else {
        await login(username, password);
      }
    } catch {
      // Error handled by AuthContext
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas flex flex-col justify-center py-12 sm:px-6 lg:px-8" dir="rtl">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="mx-auto h-14 w-14 bg-brand text-white rounded-2xl flex items-center justify-center shadow-md">
          <Newspaper className="h-8 w-8" />
        </div>
        <h2 className="mt-4 text-3xl font-extrabold text-text">InsightBot</h2>
        <p className="mt-2 text-sm text-muted">منصة استخبارات وتحليل الأخبار متعددة اللغات (محلية 100%)</p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-surface py-8 px-4 shadow sm:rounded-xl sm:px-10 border border-border">
          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-negative px-4 py-3 rounded-lg text-sm flex items-start space-x-2 space-x-reverse" role="alert">
              <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="mb-4 bg-emerald-50 border border-emerald-200 text-positive px-4 py-3 rounded-lg text-sm flex items-start space-x-2 space-x-reverse" role="alert">
              <CheckCircle2 className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <span>{successMessage}</span>
            </div>
          )}

          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-text">
                اسم المستخدم
              </label>
              <div className="mt-1 relative rounded-md shadow-sm">
                <input
                  id="username"
                  name="username"
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="block w-full pr-10 pl-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-focus focus:border-focus sm:text-sm text-text bg-white"
                  placeholder="admin أو اسم المحلل"
                />
                <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-muted">
                  <UserIcon className="h-4 w-4" />
                </div>
              </div>
            </div>

            {isRegistering && (
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-text">
                  البريد الإلكتروني (اختياري)
                </label>
                <div className="mt-1">
                  <input
                    id="email"
                    name="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="block w-full px-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-focus focus:border-focus sm:text-sm text-text bg-white"
                    placeholder="user@example.com"
                  />
                </div>
              </div>
            )}

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-text">
                كلمة المرور
              </label>
              <div className="mt-1 relative rounded-md shadow-sm">
                <input
                  id="password"
                  name="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full pr-10 pl-3 py-2 border border-border rounded-lg focus:ring-2 focus:ring-focus focus:border-focus sm:text-sm text-text bg-white"
                  placeholder="••••••••"
                />
                <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-muted">
                  <Lock className="h-4 w-4" />
                </div>
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-brand hover:bg-brand-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-focus transition-colors disabled:opacity-50"
              >
                {isSubmitting
                  ? "جاري المعالجة..."
                  : isRegistering
                  ? "إرسال طلب التسجيل"
                  : "تسجيل الدخول"}
              </button>
            </div>
          </form>

          <div className="mt-6 border-t border-border pt-4 text-center">
            <button
              type="button"
              onClick={() => {
                clearError();
                setSuccessMessage(null);
                setIsRegistering(!isRegistering);
              }}
              className="text-sm font-medium text-brand hover:underline"
            >
              {isRegistering
                ? "لديك حساب بالفعل؟ تسجيل الدخول"
                : "ليس لديك حساب؟ طلب تسجيل مستخدم جديد"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
