sha := $(shell git rev-parse --short=7 HEAD)
release_version = `cat VERSION`
_gcr := gcr.io/test6u3411ty6xqh462sri/codecov
ssh_private_key = `cat ~/.ssh/codecov-io_rsa`
build_date ?= $(shell git show -s --date=iso8601-strict --pretty=format:%cd $$sha)
name ?= worker
branch = $(shell git branch | grep \* | cut -f2 -d' ')
gh_access_token := $(shell echo ${GH_ACCESS_TOKEN})

build.local:
	docker build -f dockerscripts/Dockerfile . -t codecov/worker:latest --build-arg RELEASE_VERSION="${release_version}"

build.base:
	docker build -f dockerscripts/Dockerfile.base . -t codecov/baseworker:latest --build-arg SSH_PRIVATE_KEY="${ssh_private_key}"

build:
	$(MAKE) build.base
	$(MAKE) build.local

build.enterprise:
	docker build -f dockerscripts/Dockerfile.enterprise . -t codecov/enterprise-worker:${release_version}

# for building and pushing private images to dockerhub. This is useful if you 
# need to push a test image for enterprise to test in sandbox deployments.
build.enterprise-private: 
	docker build -f dockerscripts/Dockerfile.enterprise . -t codecov/worker-private:${release_version}-${sha}

# for portable builds to dockerhub, for use with local development and
# acceptance testing.
build.portable:
	docker build -f dockerscripts/Dockerfile . -t codecov/$(name)-portable \
		--label "org.label-schema.build-date"="$(build_date)" \
		--label "org.label-schema.name"="$(name)" \
		--label "org.label-schema.vcs-ref"="$(sha)" \
		--label "org.label-schema.vendor"="Codecov" \
		--label "org.label-schema.version"="${release_version}-${sha}" \
		--label "org.vcs-branch"="$(branch)" \
		--build-arg GH_ACCESS_TOKEN=${gh_access_token} \
		--build-arg COMMIT_SHA="${sha}" \
		--build-arg RELEASE_VERSION="${release_version}"

test:
	python -m pytest --cov=./

test.unit:
	python -m pytest --cov=./ -m "not integration" --cov-report=xml:unit.coverage.xml

test.integration:
	python -m pytest --cov=./ -m "integration" --cov-report=xml:integration.coverage.xml

push.worker-new:
	docker tag codecov/worker ${_gcr}-worker:${release_version}-${sha}
	docker push ${_gcr}-worker:${release_version}-${sha}

push.enterprise-private:
	docker push codecov/worker-private:${release_version}-${sha}

#push enterprise
push.enterprise:
	docker push codecov/enterprise-worker:${release_version}
	docker tag codecov/enterprise-worker:${release_version} codecov/enterprise-worker:latest-stable
	docker push codecov/enterprise-worker:latest-stable

# Triggers the deploy job depending on if the command is called locally, in a PR or on master.
dockerhub.deploy: dockerhub.deploy-$(release_env)

# Deploy the docker container as the latest image for master/tags.
dockerhub.deploy-master: build.portable
	docker tag codecov/$(name)-portable codecov/$(name):${release_version}-${sha}
	docker push codecov/$(name):latest
	docker push codecov/$(name):${release_version}-${sha}

update-requirements:
	pip-compile requirements.in