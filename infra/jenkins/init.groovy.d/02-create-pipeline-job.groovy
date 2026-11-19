import jenkins.model.*
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import hudson.plugins.git.GitSCM
import hudson.plugins.git.BranchSpec
import hudson.plugins.git.UserRemoteConfig

def instance = Jenkins.get()
def jobName = "vinheria-agnello-deploy"

if (instance.getItem(jobName) == null) {
    def job = instance.createProject(WorkflowJob, jobName)
    job.setDescription("Pipeline CI/CD da Vinheria Agnello - Build, Testes DevSecOps e Deploy para pasta de publicacao (simulacao IIS).")

    def remoteConfigs = [new UserRemoteConfig("file:///var/git/vinheria-agnello", null, null, null)]
    def branches = [new BranchSpec("*/main")]
    def scm = new GitSCM(remoteConfigs, branches, null, null, [])

    def definition = new CpsScmFlowDefinition(scm, "Jenkinsfile")
    definition.setLightweight(false)
    job.setDefinition(definition)
    job.save()
    println("[INIT] Job Pipeline '${jobName}' criado com sucesso.")
} else {
    println("[INIT] Job Pipeline '${jobName}' ja existe.")
}
