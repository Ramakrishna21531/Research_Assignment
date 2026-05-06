terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # backend "s3" {
  #   bucket = "your-name-terraform-state"
  #   key    = "sensor-pipeline/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "azs" {}

# ── NETWORKING ────────────────────────────────────────────────────────────────
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = { Name = "sensor-vpc" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.azs.names[count.index]
  map_public_ip_on_launch = true
  tags = { Name = "sensor-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.azs.names[count.index]
  tags = { Name = "sensor-private-${count.index}" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.igw]
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ── SECURITY GROUPS ───────────────────────────────────────────────────────────
resource "aws_security_group" "alb" {
  name   = "sensor-alb"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs" {
  name   = "sensor-ecs"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name   = "sensor-rds"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── DATABASE ──────────────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  name       = "sensor-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier             = "sensor-db"
  engine                 = "postgres"
  engine_version         = "15"
  instance_class         = var.db_instance_class
  db_name                = "sensordata"
  username               = "sensor"
  password               = var.db_password
  storage_encrypted      = true
  allocated_storage      = 20
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  publicly_accessible    = false
  deletion_protection    = false
}

# ── ECR ───────────────────────────────────────────────────────────────────────
resource "aws_ecr_repository" "api" {
  name = "sensor/api"
}

resource "aws_ecr_repository" "processor" {
  name = "sensor/processor"
}

resource "aws_ecr_repository" "frontend" {
  name = "sensor/frontend"
}

# ── ECS CLUSTER ───────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "main" {
  name = "sensor-cluster"
}

# ── GITHUB OIDC PROVIDER ──────────────────────────────────────────────────────
# Required so AWS can validate GitHub's OIDC tokens for AssumeRoleWithWebIdentity
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]

  # GitHub's OIDC thumbprint (stable, verified by GitHub docs)
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# ── IAM ROLES ─────────────────────────────────────────────────────────────────
resource "aws_iam_role" "github_actions_deploy" {
  name = "github-actions-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:Ramakrishna21531/Research_Assignment:*"
        }
      }
    }]
  })
}

resource "aws_iam_role" "ecs_exec" {
  name = "sensor-ecs-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_exec_managed" {
  role       = aws_iam_role.ecs_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "api_task_role" {
  name = "sensor-api-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role" "frontend_task_role" {
  name = "sensor-frontend-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role" "processor_task_role" {
  name = "sensor-processor-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# GitHub deploy role policy — ECS + ECR push permissions
resource "aws_iam_role_policy" "github_actions_deploy" {
  name = "github-actions-deploy-policy"
  role = aws_iam_role.github_actions_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ECR login — must be Resource "*"
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      # ECR push to our three repos
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = [
          aws_ecr_repository.api.arn,
          aws_ecr_repository.processor.arn,
          aws_ecr_repository.frontend.arn
        ]
      },
      # ECS deploy + run processor task
      {
        Effect = "Allow"
        Action = [
          "ecs:UpdateService",
          "ecs:DescribeServices",
          "ecs:RunTask",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ecs:RegisterTaskDefinition",
          "ecs:DescribeTaskDefinition"
        ]
        Resource = "*"
      },
      # Allow GitHub Actions to pass task/exec roles to ECS
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.ecs_exec.arn,
          aws_iam_role.api_task_role.arn,
          aws_iam_role.frontend_task_role.arn,
          aws_iam_role.processor_task_role.arn
        ]
      }
    ]
  })
}

# ── CLOUDWATCH LOG GROUPS ─────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/sensor-api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/sensor-frontend"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "processor" {
  name              = "/ecs/sensor-processor"
  retention_in_days = 14
}

locals {
  db_url = "postgresql://sensor:${var.db_password}@${aws_db_instance.postgres.address}:5432/sensordata"
}

# ── TASK DEFINITIONS ──────────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "api" {
  family                   = "sensor-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  task_role_arn            = aws_iam_role.api_task_role.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${aws_ecr_repository.api.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 8000
      hostPort      = 8000
      protocol      = "tcp"
    }]

    environment = [
      { name = "DATABASE_URL", value = local.db_url }
    ]

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "sensor-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  task_role_arn            = aws_iam_role.frontend_task_role.arn

  container_definitions = jsonencode([{
    name      = "frontend"
    image     = "${aws_ecr_repository.frontend.repository_url}:latest"
    essential = true

    portMappings = [{
      containerPort = 80
      hostPort      = 80
      protocol      = "tcp"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.frontend.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "frontend"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "processor" {
  family                   = "sensor-processor"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_exec.arn
  task_role_arn            = aws_iam_role.processor_task_role.arn

  container_definitions = jsonencode([{
    name      = "processor"
    image     = "${aws_ecr_repository.processor.repository_url}:latest"
    essential = true

    environment = [
      { name = "DATABASE_URL",      value = local.db_url },
      { name = "NUM_OBSERVATIONS",  value = "10000" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.processor.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "processor"
      }
    }
  }])
}

# ── LOAD BALANCER ─────────────────────────────────────────────────────────────
resource "aws_lb" "main" {
  name               = "sensor-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "api" {
  name        = "sensor-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200-399"
  }
}

resource "aws_lb_target_group" "frontend" {
  name        = "sensor-frontend"
  port        = 80
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200-399"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # Default: everything goes to the frontend
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

# Priority 10: /api/* and /api go to the API target group
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api", "/api/*", "/health"]
    }
  }
}

# ── ECS SERVICES ──────────────────────────────────────────────────────────────
resource "aws_ecs_service" "api" {
  name             = "sensor-api"
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.api.arn
  desired_count    = 2
  launch_type      = "FARGATE"
  platform_version = "LATEST"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  health_check_grace_period_seconds = 60

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "frontend" {
  name             = "sensor-frontend"
  cluster          = aws_ecs_cluster.main.id
  task_definition  = aws_ecs_task_definition.frontend.arn
  desired_count    = 1
  launch_type      = "FARGATE"
  platform_version = "LATEST"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 80
  }

  health_check_grace_period_seconds = 30

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}