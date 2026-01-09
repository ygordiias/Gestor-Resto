import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value) {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

export function formatDate(date) {
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(date));
}

export function formatDateOnly(date) {
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
  }).format(new Date(date));
}

export function getStatusColor(status) {
  const colors = {
    pending: 'status-pending',
    preparing: 'status-preparing',
    ready: 'status-ready',
    delivered: 'status-delivered',
    cancelled: 'bg-red-100 border-red-400 text-red-800',
  };
  return colors[status] || 'bg-gray-100 border-gray-400 text-gray-800';
}

export function getTableStatusColor(status) {
  const colors = {
    available: 'table-available',
    occupied: 'table-occupied',
    reserved: 'table-reserved',
    cleaning: 'table-cleaning',
  };
  return colors[status] || 'table-available';
}

export function getStatusLabel(status) {
  const labels = {
    pending: 'Pendente',
    preparing: 'Preparando',
    ready: 'Pronto',
    delivered: 'Entregue',
    cancelled: 'Cancelado',
  };
  return labels[status] || status;
}

export function getTableStatusLabel(status) {
  const labels = {
    available: 'Disponível',
    occupied: 'Ocupada',
    reserved: 'Reservada',
    cleaning: 'Limpeza',
  };
  return labels[status] || status;
}

export function getRoleLabel(role) {
  const labels = {
    admin: 'Administrador',
    waiter: 'Garçom',
    cashier: 'Caixa',
    kitchen: 'Cozinha',
    bar: 'Bar',
  };
  return labels[role] || role;
}

export function getPaymentMethodLabel(method) {
  const labels = {
    cash: 'Dinheiro',
    card: 'Cartão',
    pix: 'PIX',
    voucher: 'Vale',
  };
  return labels[method] || method;
}
