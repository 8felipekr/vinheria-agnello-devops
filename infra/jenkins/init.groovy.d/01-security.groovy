import jenkins.model.*
import hudson.security.*

def instance = Jenkins.get()

def hudsonRealm = new HudsonPrivateSecurityRealm(false)
if (hudsonRealm.getUser("admin") == null) {
    hudsonRealm.createAccount("admin", "vinheria2026")
}
instance.setSecurityRealm(hudsonRealm)

def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)

instance.save()
println("[INIT] Seguranca Jenkins configurada (usuario: admin).")
