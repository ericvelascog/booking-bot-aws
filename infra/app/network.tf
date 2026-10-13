# Red de la aplicación: una VPC con dos subredes públicas en dos zonas.
# Por qué públicas y sin NAT Gateway: docs/adr/0001-public-subnets-without-nat.md

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${local.name}-vpc" }
}

# La puerta de la VPC hacia internet
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${local.name}-igw" }
}

# count = 2: Terraform crea dos copias de este bloque, una por zona.
# count.index vale 0 en la primera y 1 en la segunda:
#   10.0.1.0/24 en eu-west-1a y 10.0.2.0/24 en eu-west-1b
resource "aws_subnet" "public" {
  count = length(local.azs)

  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = local.azs[count.index]

  tags = { Name = "${local.name}-public-${local.azs[count.index]}" }
}

# El cartel indicador: todo lo que vaya a internet sale por la puerta (IGW)
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name}-public" }
}

# Colgar el cartel en las dos subredes (esto es lo que las hace "públicas")
resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
