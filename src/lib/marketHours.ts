/**
 * Indian Stock Market (NSE/BSE) Hours & Status Engine
 * Standard Trading Hours: Monday - Friday, 09:15 to 15:30 IST
 * Safe Intraday Square-Off Time: 15:15 IST
 */

export interface MarketHoursInfo {
  isOpen: boolean;
  isWeekday: boolean;
  isPreMarket: boolean;
  isPostMarket: boolean;
  isSafeExitPassed: boolean;
  secondsToClose: number;
  secondsToOpen: number;
  istTimeString: string;
  istDateString: string;
  statusText: string;
}

export function getMarketHoursInfo(): MarketHoursInfo {
  const now = new Date();
  
  // Format to Asia/Kolkata (IST = UTC+5:30)
  const istString = now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' });
  const istDate = new Date(istString);

  const day = istDate.getDay(); // 0 = Sunday, 6 = Saturday
  const isWeekday = day >= 1 && day <= 5;
  
  const hours = istDate.getHours();
  const minutes = istDate.getMinutes();
  const seconds = istDate.getSeconds();
  const totalSeconds = hours * 3600 + minutes * 60 + seconds;

  const preMarketOpenSecs = 9 * 3600;            // 09:00 IST
  const marketOpenSecs = 9 * 3600 + 15 * 60;      // 09:15 IST (33,300s)
  const safeExitSecs = 15 * 3600 + 15 * 60;       // 15:15 IST (54,900s)
  const marketCloseSecs = 15 * 3600 + 30 * 60;    // 15:30 IST (55,800s)

  const isPreMarket = isWeekday && totalSeconds >= preMarketOpenSecs && totalSeconds < marketOpenSecs;
  const isOpen = isWeekday && totalSeconds >= marketOpenSecs && totalSeconds < marketCloseSecs;
  const isSafeExitPassed = !isWeekday || totalSeconds >= safeExitSecs || totalSeconds < marketOpenSecs;
  const isPostMarket = isWeekday && totalSeconds >= marketCloseSecs;

  const secondsToClose = isOpen ? Math.max(0, marketCloseSecs - totalSeconds) : 0;
  
  let secondsToOpen = 0;
  if (!isOpen) {
    if (isWeekday && totalSeconds < marketOpenSecs) {
      secondsToOpen = marketOpenSecs - totalSeconds;
    } else {
      // Calculate seconds to next 09:15 AM
      let daysUntilNext = 1;
      if (day === 5) daysUntilNext = 3; // Friday -> Monday
      else if (day === 6) daysUntilNext = 2; // Saturday -> Monday
      else if (day === 0) daysUntilNext = 1; // Sunday -> Monday
      
      const remainingToday = Math.max(0, 24 * 3600 - totalSeconds);
      secondsToOpen = remainingToday + (daysUntilNext - 1) * 24 * 3600 + marketOpenSecs;
    }
  }

  let statusText = 'MARKET CLOSED';
  if (isOpen) {
    statusText = totalSeconds >= safeExitSecs ? 'CLOSING SOON (AUTO SQUARE-OFF)' : 'MARKET OPEN';
  } else if (isPreMarket) {
    statusText = 'PRE-MARKET SESSION';
  } else if (!isWeekday) {
    statusText = 'WEEKEND (MARKET CLOSED)';
  }

  const istTimeString = istDate.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });

  const istDateString = istDate.toLocaleDateString('en-IN', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });

  return {
    isOpen,
    isWeekday,
    isPreMarket,
    isPostMarket,
    isSafeExitPassed,
    secondsToClose,
    secondsToOpen,
    istTimeString,
    istDateString,
    statusText,
  };
}

export function isMarketOpenNow(): boolean {
  return getMarketHoursInfo().isOpen;
}

export function isSafeSquareoffTimeNow(): boolean {
  return getMarketHoursInfo().isSafeExitPassed;
}
