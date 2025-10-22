"""
Agent Summarizer installer implementing PRIME_DIRECTIVE contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from installer import (
    ApplyResult,
    ApplyStatus,
    DeploymentPlan,
    DeploymentStep,
    Installer,
    PermissionScope,
    Requirements,
    Resources,
    RollbackResult,
    ValidationResult,
    ValidationStatus,
    VerificationReport,
)
from installer.railway import RailwayProvider


class AgentSummarizerInstaller(Installer):
    """Installer for Agent Summarizer service."""

    def __init__(self) -> None:
        super().__init__(capability_name="agent-summarizer", version="1.0.0")
        self.service_name = "budai-agent-summarizer"

    def describe_requirements(self, env: str) -> Requirements:
        return Requirements(
            capability="agent-summarizer",
            version="1.0.0",
            permissions=[
                PermissionScope(provider="railway", service="project", action="create_service", scope="project-level"),
                PermissionScope(provider="openai", service="api", action="chat.completions", scope="api-key"),
            ],
            dependencies=[
                {"type": "network", "needs": ["egress to api.openai.com:443"], "name": None, "port": None},
                {"type": "service", "name": "redis", "port": 6379, "needs": []},
            ],
            resources=Resources(memory_mb=512, cpu_millicores=500),
            estimated_cost_floor_usd=10.0,
        )

    def validate_permissions(self, creds: dict, env: str) -> ValidationResult:
        validated, missing, errors = [], [], []
        if "railway_token" in creds:
            validated.append(PermissionScope(provider="railway", service="project", action="create_service", scope="project-level"))
        if "openai_api_key" in creds:
            validated.append(PermissionScope(provider="openai", service="api", action="chat.completions", scope="api-key"))
        else:
            missing.append(PermissionScope(provider="openai", service="api", action="chat.completions", scope="api-key"))
            errors.append("OpenAI API key not provided")
        return ValidationResult(status=ValidationStatus.VALID if not missing else ValidationStatus.INVALID, validated_permissions=validated, missing_permissions=missing, validation_errors=errors)

    def plan(self, spec: dict, env: str) -> DeploymentPlan:
        steps = [
            DeploymentStep(id="railway.create_service", action="create_railway_service", params={"service_name": self.service_name, "environment": env}, retriable=True),
            DeploymentStep(id="env.set_variables", action="set_environment_variables", params={"variables": {"BUDAI_SERVICE_NAME": "agent-summarizer", "PORT": "8002"}}, retriable=True, depends_on=["railway.create_service"]),
            DeploymentStep(id="railway.deploy", action="trigger_deployment", params={"service_name": self.service_name, "wait_for_health": True}, retriable=False, depends_on=["env.set_variables"]),
        ]
        return DeploymentPlan(target_env=env, capability="agent-summarizer", version="1.0.0", steps=steps, rollback=[], invariants=[], checksum="")

    def apply(self, plan: DeploymentPlan, creds: dict) -> ApplyResult:
        import time
        start_time = time.time()
        applied_steps = []
        artifacts = {}
        
        try:
            railway = RailwayProvider(api_token=creds["railway_token"], project_id=creds.get("railway_project_id"))
            for step in plan.steps:
                if step.action == "create_railway_service":
                    target_env = step.params.get("environment", plan.target_env)
                    artifacts["service_id"] = railway.create_service(
                        name=step.params["service_name"],
                        source_repo=creds.get("github_repo"),
                        source_branch=creds.get("github_branch", "main"),
                        environment=target_env,
                    )
                    artifacts["environment"] = target_env
                    
                    # Configure root directory for monorepo - Railway will auto-detect railway.json
                    service_id = artifacts["service_id"]
                    env_id = railway._get_environment_id(railway.project_id, target_env)
                    artifacts["environment_id"] = env_id
                    
                    try:
                        railway.service_instance_update(
                            service_id=service_id,
                            environment_id=env_id,
                            root_directory="services/agent-summarizer",
                        )
                        self.logger.info("Successfully configured root directory for monorepo")
                    except Exception as e:
                        self.logger.warning("Failed to configure root directory: %s", e)
                        self.logger.warning("Service will be created but may need manual configuration of root directory")
                elif step.action == "set_environment_variables":
                    variables = dict(step.params["variables"])
                    redis_url = creds.get("redis_url")
                    if redis_url:
                        variables.setdefault("REDIS_URL", redis_url)
                        variables.setdefault("BUDAI_REDIS_URL", redis_url)
                    if creds.get("redis_password"):
                        variables.setdefault("REDIS_PASSWORD", creds["redis_password"])
                    if creds.get("redis_host"):
                        variables.setdefault("REDIS_HOST", creds["redis_host"])
                    if creds.get("redis_port"):
                        variables.setdefault("REDIS_PORT", str(creds["redis_port"]))
                    railway.set_environment_variables(artifacts["service_id"], plan.target_env, variables)
                elif step.action == "trigger_deployment":
                    artifacts["deployment_id"] = railway.deploy_service(
                        service_id=artifacts["service_id"],
                        environment=artifacts.get("environment", plan.target_env),
                    )
                    if step.params.get("wait_for_health"):
                        railway.wait_for_deployment(artifacts["deployment_id"], timeout_seconds=600)
                applied_steps.append(step.id)
            
            return ApplyResult(status=ApplyStatus.SUCCESS, applied_steps=applied_steps, duration_seconds=time.time() - start_time, artifacts=artifacts)
        except Exception as exc:
            return ApplyResult(status=ApplyStatus.FAILED, applied_steps=applied_steps, error_message=str(exc), duration_seconds=time.time() - start_time, artifacts=artifacts)

    def verify(self, env: str) -> VerificationReport:
        return VerificationReport(capability="agent-summarizer", environment=env, overall_status="healthy", health_checks=[], slis={})

    def rollback(self, plan: DeploymentPlan, creds: dict) -> RollbackResult:
        import time
        return RollbackResult(status=ApplyStatus.SUCCESS, rolled_back_steps=[], duration_seconds=0.1)

